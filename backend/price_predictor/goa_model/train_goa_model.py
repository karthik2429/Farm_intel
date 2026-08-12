#!/usr/bin/env python3
"""
Goa Price Prediction Model Training
Features: Lag/Rolling prices, Weather (synthetic Goa climate), Calendar/Seasonal/Festival, 
          Arrivals/Supply, Commodity-specific features
Target: 14-day ahead modal price prediction
Models: XGBoost (primary) + LSTM (sequence model)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import joblib
import json
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# ML imports
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
import xgboost as xgb

warnings.filterwarnings("ignore")

# ─── PATHS ────────────────────────────────────────────────────────────────
DATA_PATH = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/goa_merged/goa_merged_historical.parquet")
MODEL_DIR = Path("/Users/karthik/Desktop/Capstone copy/collab/price_predictor/goa_model")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ─── GOA CLIMATE CONFIG ───────────────────────────────────────────────────
MONSOON_MONTHS = [6, 7, 8, 9]
POST_MONSOON_MONTHS = [10, 11]
WINTER_MONTHS = [12, 1, 2]
SUMMER_MONTHS = [3, 4, 5]

GOA_FESTIVALS = {
    "carnival": (2, 1, 2, 15),
    "shigmo": (3, 1, 3, 31),
    "ganesh_chaturthi": (8, 15, 9, 15),
    "diwali": (10, 15, 11, 15),
    "christmas": (12, 20, 12, 31),
    "new_year": (1, 1, 1, 5),
    "sao_joao": (6, 20, 6, 30),
}

COMMODITY_CATEGORIES = {
    "perishable": ["Tomato", "Onion", "Potato", "Banana", "Papaya", "Mango", "Pineapple", 
                   "Watermelon", "Green Chilli", "Brinjal", "Coconut", "Orange", "Apple", 
                   "Grapes", "Rose(Loose)", "Marigold(Loose)", "Water Melon", "Papaya"],
    "storage": ["Arecanut(Betelnut/Supari)", "Cashewnuts", "Copra"],
    "cereals": ["Rice", "Wheat", "Maize"],
    "pulses": ["Gram", "Arhar/Tur", "Moong", "Urad"],
    "oilseeds": ["Groundnut", "Soybean", "Mustard", "Sunflower", "Sesamum"],
    "spices": ["Turmeric", "Chilli", "Cumin", "Coriander", "Pepper", "Cardamom"],
}


# ─── FEATURE ENGINEERING ──────────────────────────────────────────────────

def create_multistep_targets(df: pd.DataFrame, group_cols: List[str], 
                              horizons: List[int] = [1, 3, 7, 14]) -> pd.DataFrame:
    """Create multi-horizon target columns."""
    df = df.copy()
    df = df.sort_values(group_cols + ["arrival_date"])
    for h in horizons:
        df[f"target_{h}d"] = df.groupby(group_cols)["modal_price"].shift(-h)
    df["target"] = df["target_14d"]  # Primary target
    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar, seasonal, and festival features."""
    df = df.copy()
    dt = df["arrival_date"]
    
    df["year"] = dt.dt.year
    df["month"] = dt.dt.month
    df["day"] = dt.dt.day
    df["day_of_week"] = dt.dt.dayofweek
    df["day_of_year"] = dt.dt.dayofyear
    df["week_of_year"] = dt.dt.isocalendar().week
    df["quarter"] = dt.dt.quarter
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    
    # Indian agricultural seasons
    def get_season(m):
        if m in MONSOON_MONTHS:
            return "Monsoon_Kharif"
        elif m in POST_MONSOON_MONTHS:
            return "Post_Monsoon_Harvest"
        elif m in WINTER_MONTHS:
            return "Winter_Rabi"
        else:
            return "Summer_Zaid"
    
    df["season"] = df["month"].apply(get_season)
    
    df["is_monsoon"] = df["month"].isin(MONSOON_MONTHS).astype(int)
    df["is_post_monsoon"] = df["month"].isin(POST_MONSOON_MONTHS).astype(int)
    df["is_winter"] = df["month"].isin(WINTER_MONTHS).astype(int)
    df["is_summer"] = df["month"].isin(SUMMER_MONTHS).astype(int)
    
    # Cyclical encoding
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["day_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365)
    df["day_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365)
    
    # Festival indicators
    for fest, (sm, sd, em, ed) in GOA_FESTIVALS.items():
        mask = (
            ((df["month"] > sm) | ((df["month"] == sm) & (df["day"] >= sd))) &
            ((df["month"] < em) | ((df["month"] == em) & (df["day"] <= ed)))
        )
        df[f"is_{fest}"] = mask.astype(int)
    
    df["festival_intensity"] = sum(df[f"is_{f}"] for f in GOA_FESTIVALS)
    
    # Harvest windows
    df["is_kharif_harvest"] = df["month"].isin([10, 11, 12]).astype(int)
    df["is_rabi_harvest"] = df["month"].isin([3, 4, 5]).astype(int)
    
    return df


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add synthetic Goa coastal tropical weather features."""
    df = df.copy()
    
    # Goa climate: coastal, tropical, high humidity
    def temp_max(m):
        base = 33
        if m in SUMMER_MONTHS: return base + 3
        elif m in MONSOON_MONTHS: return base - 2
        elif m in WINTER_MONTHS: return base - 4
        return base
    
    def temp_min(m):
        base = 22
        if m in WINTER_MONTHS: return base - 3
        elif m in MONSOON_MONTHS: return base + 2
        return base
    
    def rainfall(m):
        if m in MONSOON_MONTHS:
            return np.random.gamma(2, 400) if m in [7, 8] else np.random.gamma(2, 200)
        elif m in POST_MONSOON_MONTHS:
            return np.random.exponential(50)
        return np.random.exponential(5)
    
    def humidity(m):
        base = 75
        if m in MONSOON_MONTHS: return np.clip(base + np.random.normal(0, 5), 80, 95)
        elif m in POST_MONSOON_MONTHS: return np.clip(base + np.random.normal(0, 8), 70, 85)
        elif m in WINTER_MONTHS: return np.clip(base + np.random.normal(0, 10), 55, 75)
        return np.clip(base + np.random.normal(0, 10), 60, 80)
    
    df["temp_max_est"] = df["month"].apply(temp_max)
    df["temp_min_est"] = df["month"].apply(temp_min)
    df["temp_avg_est"] = (df["temp_max_est"] + df["temp_min_est"]) / 2
    df["temp_range_est"] = df["temp_max_est"] - df["temp_min_est"]
    df["rainfall_est"] = df["month"].apply(rainfall)
    df["humidity_est"] = df["month"].apply(humidity)
    
    # Weather stress
    df["heat_stress"] = (df["temp_max_est"] > 35).astype(int)
    df["cold_stress"] = (df["temp_min_est"] < 18).astype(int)
    df["drought_stress"] = ((df["rainfall_est"] < 10) & ~df["month"].isin(MONSOON_MONTHS)).astype(int)
    df["flood_risk"] = (df["rainfall_est"] > 500).astype(int)
    
    # Rolling weather
    for window in [7, 30]:
        df[f"rainfall_ma{window}"] = df.groupby(["district", "commodity"])["rainfall_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"humidity_ma{window}"] = df.groupby(["district", "commodity"])["humidity_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"temp_avg_ma{window}"] = df.groupby(["district", "commodity"])["temp_avg_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
    
    return df


def add_lag_rolling_features(df: pd.DataFrame, group_cols: List[str] = None) -> pd.DataFrame:
    """Add lag and rolling window features for price and arrivals."""
    if group_cols is None:
        group_cols = ["district", "commodity", "market"]
    
    df = df.copy()
    df = df.sort_values(group_cols + ["arrival_date"]).reset_index(drop=True)
    
    target = "modal_price"
    arrival = "arrival_tonnes"
    
    # Ensure arrival column exists
    if arrival not in df.columns:
        df[arrival] = np.random.uniform(10, 5000, len(df))
    
    # Price lags
    for lag in [1, 2, 3, 7, 14, 30]:
        df[f"price_lag_{lag}"] = df.groupby(group_cols)[target].shift(lag)
    
    # Price rolling stats
    for window in [3, 7, 14, 30]:
        df[f"price_ma_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"price_std_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=2).std()
        )
        df[f"price_min_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=1).min()
        )
        df[f"price_max_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=1).max()
        )
        
        # Momentum
        df[f"price_momentum_{window}"] = df[f"price_ma_{window}"] / (df[f"price_lag_{window}"] + 1) - 1
        
        # Coefficient of variation
        df[f"price_cv_{window}"] = df[f"price_std_{window}"] / (df[f"price_ma_{window}"] + 1)
    
    # Price changes
    for lag in [1, 7, 14]:
        df[f"price_change_{lag}d"] = df.groupby(group_cols)[target].pct_change(lag)
    
    # Arrival features
    for lag in [1, 7, 14]:
        df[f"arrival_lag_{lag}"] = df.groupby(group_cols)[arrival].shift(lag)
    
    for window in [7, 14, 30]:
        df[f"arrival_ma_{window}"] = df.groupby(group_cols)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"arrival_sum_{window}"] = df.groupby(group_cols)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).sum()
        )
    
    # Supply pressure
    df["supply_pressure"] = df[arrival] / (df["arrival_ma_30"] + 1)
    df["supply_pressure_7d"] = df[arrival] / (df["arrival_ma_7"] + 1)
    
    # Price spread
    df["price_spread"] = df["max_price"] - df["min_price"]
    df["price_spread_pct"] = df["price_spread"] / (df["modal_price"] + 1)
    
    return df


def add_commodity_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add commodity-specific categorical and seasonal features."""
    df = df.copy()
    
    for cat, items in COMMODITY_CATEGORIES.items():
        df[f"is_{cat}"] = df["commodity"].isin(items).astype(int)
    
    # Perishability score
    df["perishability_score"] = df["is_perishable"] * 2 + df["is_storage"] * (-1)
    
    # Seasonal alignment
    df["cereal_kharif"] = (df["is_cereals"] & df["month"].isin([6, 7, 8, 9, 10])).astype(int)
    df["cereal_rabi"] = (df["is_cereals"] & df["month"].isin([11, 12, 1, 2, 3, 4])).astype(int)
    df["pulse_kharif"] = (df["is_pulses"] & df["month"].isin([6, 7, 8, 9])).astype(int)
    df["pulse_rabi"] = (df["is_pulses"] & df["month"].isin([10, 11, 12, 1, 2, 3])).astype(int)
    
    return df


def encode_categoricals(df: pd.DataFrame, encoders: Dict = None, fit: bool = True) -> Tuple[pd.DataFrame, Dict]:
    """Encode categorical features."""
    df = df.copy()
    cat_cols = ["district", "commodity", "variety", "grade", "market", "season"]
    
    if encoders is None:
        encoders = {}
    
    for col in cat_cols:
        if col not in df.columns:
            continue
        
        if fit:
            le = LabelEncoder()
            df[f"{col}_enc"] = le.fit_transform(df[col].astype(str).fillna("Unknown"))
            encoders[col] = le
        else:
            le = encoders.get(col)
            if le:
                # Handle unseen categories
                known = set(le.classes_)
                df[col] = df[col].astype(str).apply(lambda x: x if x in known else "Unknown")
                df[f"{col}_enc"] = le.transform(df[col])
            else:
                df[f"{col}_enc"] = 0
    
    return df, encoders


def create_training_dataset(df: pd.DataFrame, target_horizon: int = 14) -> Tuple[pd.DataFrame, pd.Series, List[str], Dict]:
    """Create supervised learning dataset for multi-step price prediction."""
    group_cols = ["district", "commodity", "market"]
    
    print("🔧 Engineering features...")
    df = add_calendar_features(df)
    df = add_weather_features(df)
    df = add_lag_rolling_features(df, group_cols)
    df = add_commodity_features(df)
    df = create_multistep_targets(df, group_cols, horizons=[1, 3, 7, 14])
    df, encoders = encode_categoricals(df, fit=True)
    
    # Feature columns (exclude non-feature columns)
    exclude_cols = [
        "arrival_date", "target", "target_1d", "target_3d", "target_7d", "target_14d",
        "state", "district", "commodity", "variety", "grade", "market", "season"
    ]
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # Clean: replace inf and large values
    for col in feature_cols:
        if df[col].dtype in ['float64', 'float32', 'int64', 'int32']:
            df[col] = df[col].replace([np.inf, -np.inf], np.nan)
            df[col] = df[col].fillna(df[col].median())
    
    # Target: 14-day percentage change (more stable across commodities)
    df["target_pct"] = df["target_14d"] / (df["modal_price"] + 1) - 1
    
    # Clip extreme percentage changes per commodity
    pct_caps = df.groupby("commodity")["target_pct"].transform(lambda x: x.quantile(0.99))
    pct_floors = df.groupby("commodity")["target_pct"].transform(lambda x: x.quantile(0.01))
    df["target_pct_clipped"] = df["target_pct"].clip(lower=pct_floors, upper=pct_caps)
    
    # Drop rows with NaN target
    df_clean = df.dropna(subset=["target_pct_clipped"]).copy()
    
    # Final fill for any remaining NaN
    for col in feature_cols:
        if df_clean[col].isna().any():
            df_clean[col] = df_clean[col].fillna(0)
    
    X = df_clean[feature_cols]
    y = df_clean["target_pct_clipped"]
    
    print(f"✅ Training dataset: {X.shape[0]:,} samples, {X.shape[1]} features")
    print(f"   Target stats: mean={y.mean():.4f}, std={y.std():.4f}, min={y.min():.4f}, max={y.max():.4f}")
    
    return X, y, feature_cols, encoders


# ─── MODEL TRAINING ───────────────────────────────────────────────────────

def train_xgboost(X: pd.DataFrame, y: pd.Series, feature_cols: List[str], 
                  encoders: Dict, params: Dict = None) -> Dict:
    """Train XGBoost model with time-series split."""
    
    if params is None:
        params = {
            "objective": "reg:squarederror",
            "n_estimators": 500,
            "max_depth": 8,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "n_jobs": -1,
            "early_stopping_rounds": 50,
        }
    
    # Time series split: last 20% as test
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"📊 Train: {len(X_train):,}, Test: {len(X_test):,}")
    
    model = xgb.XGBRegressor(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50
    )
    
    # Predictions
    y_pred = model.predict(X_test)
    
    # Metrics
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    # For percentage target, MAPE doesn't make sense, use symmetric MAPE
    mape = np.mean(2 * np.abs(y_test - y_pred) / (np.abs(y_test) + np.abs(y_pred) + 1e-8)) * 100
    
    print(f"\n📈 XGBoost Performance (on % change target):")
    print(f"   MAE:  {mae:.4f} ({mae*100:.2f}%)")
    print(f"   RMSE: {rmse:.4f} ({rmse*100:.2f}%)")
    print(f"   R²:   {r2:.4f}")
    print(f"   SMAPE: {mape:.2f}%")
    
    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)
    
    print(f"\n🔝 Top 20 Features:")
    for _, row in importance.head(20).iterrows():
        print(f"   {row['feature']}: {row['importance']:.4f}")
    
    # Save artifacts
    artifacts = {
        "model": model,
        "feature_cols": feature_cols,
        "encoders": encoders,
        "params": params,
        "metrics": {
            "mae": float(mae), "rmse": float(rmse), 
            "r2": float(r2), "mape": float(mape)
        },
        "feature_importance": importance.to_dict("records"),
        "trained_at": datetime.now().isoformat(),
        "n_train_samples": int(len(X_train)),
        "model_type": "XGBoost"
    }
    
    joblib.dump(artifacts, MODEL_DIR / "goa_xgb_model.pkl")
    print(f"\n💾 Model saved to {MODEL_DIR / 'goa_xgb_model.pkl'}")
    
    return artifacts


def create_lstm_sequences(X: pd.DataFrame, y: pd.Series, sequence_length: int = 30, 
                          group_cols: List[str] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Create sequences for LSTM training."""
    if group_cols is None:
        group_cols = ["district", "commodity", "market"]
    
    # We need the original dataframe with group columns to create sequences
    # This is a simplified version - in practice, you'd pass the full dataframe
    sequences = []
    targets = []
    
    # For each group, create sequences
    # This requires the original dataframe with group info
    # We'll use a simplified approach here
    return np.array(sequences), np.array(targets)


def train_lstm_model(X: pd.DataFrame, y: pd.Series, feature_cols: List[str], 
                     encoders: Dict, df_full: pd.DataFrame) -> Dict:
    """Train LSTM model for sequence-based prediction."""
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
        from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
        from tensorflow.keras.optimizers import Adam
    except ImportError:
        print("⚠️ TensorFlow not available, skipping LSTM")
        return None
    
    print("\n🧠 Training LSTM model...")
    
    group_cols = ["district", "commodity", "market"]
    sequence_length = 30
    
    # Prepare sequences per group
    df_full = df_full.sort_values(group_cols + ["arrival_date"])
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Create sequences
    X_seq, y_seq = [], []
    for _, group in df_full.groupby(group_cols):
        if len(group) < sequence_length + 14:
            continue
        
        group_X = group[feature_cols].values
        group_y = group["target_price_14d"].values
        
        for i in range(len(group) - sequence_length - 14 + 1):
            X_seq.append(group_X[i:i+sequence_length])
            y_seq.append(group_y[i+sequence_length-1])
    
    if len(X_seq) == 0:
        print("   Not enough data for sequences")
        return None
    
    X_seq = np.array(X_seq)
    y_seq = np.array(y_seq)
    
    print(f"   Sequences: {X_seq.shape[0]:,}, Length: {sequence_length}, Features: {X_seq.shape[2]}")
    
    # Split
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    
    # Build model
    model = Sequential([
        LSTM(128, return_sequences=True, input_shape=(sequence_length, len(feature_cols))),
        BatchNormalization(),
        Dropout(0.2),
        LSTM(64, return_sequences=False),
        BatchNormalization(),
        Dropout(0.2),
        Dense(32, activation='relu'),
        Dense(1)
    ])
    
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
    
    callbacks = [
        EarlyStopping(patience=15, restore_best_weights=True),
        ReduceLROnPlateau(patience=10, factor=0.5)
    ]
    
    history = model.fit(
        X_train, y_train,
        validation_data=(X_test, y_test),
        epochs=100,
        batch_size=64,
        callbacks=callbacks,
        verbose=1
    )
    
    # Evaluate
    y_pred = model.predict(X_test, verbose=0).flatten()
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    
    print(f"\n📈 LSTM Performance:")
    print(f"   MAE:  ₹{mae:.2f}")
    print(f"   RMSE: ₹{rmse:.2f}")
    print(f"   R²:   {r2:.4f}")
    
    # Save
    model.save(MODEL_DIR / "goa_lstm_model.h5")
    joblib.dump({"scaler": scaler, "sequence_length": sequence_length}, MODEL_DIR / "lstm_preprocessing.pkl")
    
    artifacts = {
        "model_path": str(MODEL_DIR / "goa_lstm_model.h5"),
        "scaler": scaler,
        "sequence_length": sequence_length,
        "feature_cols": feature_cols,
        "metrics": {"mae": float(mae), "rmse": float(rmse), "r2": float(r2)},
        "model_type": "LSTM"
    }
    
    return artifacts


# ─── PREDICTION ───────────────────────────────────────────────────────────

def prepare_latest_features(df: pd.DataFrame, encoders: Dict, feature_cols: List[str]) -> pd.DataFrame:
    """Prepare features for the latest date per commodity-market group."""
    group_cols = ["district", "commodity", "market"]
    
    # Apply same feature engineering
    df = add_calendar_features(df)
    df = add_weather_features(df)
    df = add_lag_rolling_features(df, group_cols)
    df = add_commodity_features(df)
    df, _ = encode_categoricals(df, encoders, fit=False)
    
    # Get latest row per group
    latest = df.sort_values("arrival_date").groupby(group_cols).tail(1)
    
    # Ensure all feature columns present
    for col in feature_cols:
        if col not in latest.columns:
            latest[col] = 0
    
    return latest[group_cols + ["arrival_date", "modal_price"] + feature_cols]


def predict_14_day(model_artifacts: Dict, df_history: pd.DataFrame, 
                   group_cols: List[str] = None) -> pd.DataFrame:
    """Generate 14-day price predictions using full history for lag features."""
    if group_cols is None:
        group_cols = ["district", "commodity", "market"]
    
    model = model_artifacts["model"]
    feature_cols = model_artifacts["feature_cols"]
    encoders = model_artifacts["encoders"]
    
    # Use full history to compute lag/rolling features, then take latest
    df = df_history.sort_values(group_cols + ["arrival_date"]).copy()
    df = add_calendar_features(df)
    df = add_weather_features(df)
    df = add_lag_rolling_features(df, group_cols)
    df = add_commodity_features(df)
    df, _ = encode_categoricals(df, encoders, fit=False)
    
    # Get latest row per group
    df_latest = df.groupby(group_cols).tail(1).copy()
    
    # Ensure all feature columns present
    for col in feature_cols:
        if col not in df_latest.columns:
            df_latest[col] = 0
    
    # Handle duplicate columns
    df_latest = df_latest.loc[:, ~df_latest.columns.duplicated()]
    
    X_pred = df_latest[feature_cols]
    
    # Predict percentage change
    pred_pct = model.predict(X_pred)
    
    # Convert back to price
    current_price = df_latest["modal_price"].values
    pred_price = current_price * (1 + pred_pct)
    
    results = df_latest[group_cols + ["arrival_date", "modal_price"]].copy()
    results["predicted_price_14d"] = pred_price
    results["predicted_change_pct"] = (pred_pct * 100).round(2)
    results["prediction_date"] = datetime.now().date()
    results["model"] = "XGBoost"
    
    return results


def generate_trajectory(model_artifacts: Dict, df_latest_row: pd.DataFrame,
                        feature_cols: List[str], group_cols: List[str],
                        steps: int = 14) -> pd.DataFrame:
    """Generate day-by-day 14-day price trajectory."""
    model = model_artifacts["model"]
    encoders = model_artifacts["encoders"]
    
    # For each group, iteratively predict
    all_trajectories = []
    
    for _, row in df_latest_row.iterrows():
        group_key = {col: row[col] for col in group_cols}
        current_features = row[feature_cols].copy()
        current_date = row["arrival_date"]
        
        trajectory = []
        for day in range(1, steps + 1):
            # Predict next day
            X_pred = pd.DataFrame([current_features])[feature_cols]
            pred = model.predict(X_pred)[0]
            
            trajectory.append({
                **group_key,
                "prediction_day": day,
                "prediction_date": current_date + timedelta(days=day),
                "predicted_price": pred,
                "confidence": max(0.5, 1.0 - day * 0.03)  # Decreasing confidence
            })
            
            # Update features for next iteration (simplified)
            # Shift lags
            for lag in [30, 14, 7, 3, 2, 1]:
                if f"price_lag_{lag}" in current_features:
                    if lag == 1:
                        current_features["price_lag_1"] = pred
                    else:
                        current_features[f"price_lag_{lag}"] = current_features.get(f"price_lag_{lag-1}", pred)
            
            # Update rolling means (approximate)
            for window in [3, 7, 14, 30]:
                if f"price_ma_{window}" in current_features:
                    current_features[f"price_ma_{window}"] = pred  # Simplified
            
            current_date += timedelta(days=1)
        
        all_trajectories.append(pd.DataFrame(trajectory))
    
    if all_trajectories:
        return pd.concat(all_trajectories, ignore_index=True)
    return pd.DataFrame()


def generate_14_day_trajectory(model_artifacts: Dict, df_latest: pd.DataFrame, 
                               df_history: pd.DataFrame, steps: int = 14) -> pd.DataFrame:
    """Generate day-by-day 14-day trajectory using iterative prediction."""
    model = model_artifacts["model"]
    feature_cols = model_artifacts["feature_cols"]
    encoders = model_artifacts["encoders"]
    group_cols = ["district", "commodity", "market"]
    
    # Sort history
    df_history = df_history.sort_values(group_cols + ["arrival_date"])
    
    all_predictions = []
    
    for _, group in df_history.groupby(group_cols):
        # Get last known row
        last_row = group.tail(1).copy()
        if len(last_row) == 0:
            continue
        
        current_features = last_row[feature_cols].values.flatten()
        current_price = last_row["modal_price"].values[0]
        current_date = last_row["arrival_date"].values[0]
        
        trajectory = []
        
        for day in range(1, steps + 1):
            # Predict next day
            pred = model.predict(current_features.reshape(1, -1))[0]
            
            trajectory.append({
                "district": last_row["district"].values[0],
                "commodity": last_row["commodity"].values[0],
                "market": last_row["market"].values[0],
                "prediction_date": current_date + timedelta(days=day),
                "day_ahead": day,
                "predicted_price": pred,
                "current_price": current_price
            })
            
            # Update features for next iteration (simplified)
            # In production, you'd properly update all lag/rolling features
            current_price = pred
        
        all_predictions.extend(trajectory)
    
    return pd.DataFrame(all_predictions)


# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("GOA MARKET PRICE PREDICTION - MODEL TRAINING")
    print("=" * 60)
    
    # Load data
    print("\n📥 Loading Goa merged dataset...")
    df = pd.read_parquet(DATA_PATH)
    print(f"   Loaded: {len(df):,} records")
    print(f"   Date range: {df['arrival_date'].min()} to {df['arrival_date'].max()}")
    print(f"   Commodities: {df['commodity'].nunique()}")
    print(f"   Markets: {df['market'].nunique()}")
    print(f"   Districts: {df['district'].unique()}")
    
    # Filter out APMC markets (different price units)
    df = df[~df['market'].str.contains('APMC', case=False)].copy()
    print(f"\n   After filtering APMC: {len(df):,} records, {df['market'].nunique()} markets")
    
    # Remove extreme outliers per commodity-market
    df_clean = df.copy()
    for (comm, mkt), group in df_clean.groupby(['commodity', 'market']):
        q01 = group['modal_price'].quantile(0.01)
        q99 = group['modal_price'].quantile(0.99)
        df_clean = df_clean[~((df_clean['commodity'] == comm) & (df_clean['market'] == mkt) & 
                              ((df_clean['modal_price'] < q01) | (df_clean['modal_price'] > q99)))]
    
    print(f"   After outlier removal: {len(df_clean):,} records")
    df = df_clean
    
    # Ensure required columns
    if "arrival_tonnes" not in df.columns:
        df["arrival_tonnes"] = np.random.uniform(10, 5000, len(df))
    
    # Create training dataset
    X, y, feature_cols, encoders = create_training_dataset(df, target_horizon=14)
    
    # Train XGBoost
    print("\n" + "=" * 60)
    print("TRAINING XGBOOST MODEL")
    print("=" * 60)
    xgb_artifacts = train_xgboost(X, y, feature_cols, encoders)
    
    # Train LSTM (optional)
    print("\n" + "=" * 60)
    print("TRAINING LSTM MODEL")
    print("=" * 60)
    lstm_artifacts = train_lstm_model(X, y, feature_cols, encoders, df)
    
    # Save combined metadata
    metadata = {
        "xgb": {k: v for k, v in xgb_artifacts.items() if k != "model"},
        "lstm": lstm_artifacts,
        "feature_cols": feature_cols,
        "n_commodities": int(df["commodity"].nunique()),
        "n_markets": int(df["market"].nunique()),
        "date_range": {
            "start": str(df["arrival_date"].min()),
            "end": str(df["arrival_date"].max())
        },
        "trained_at": datetime.now().isoformat()
    }
    
    with open(MODEL_DIR / "goa_model_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    print("\n✅ TRAINING COMPLETE!")
    print(f"   Models saved to: {MODEL_DIR}")
    print(f"   XGBoost MAE (log-ret): {xgb_artifacts['metrics']['mae']:.4f}")
    if lstm_artifacts:
        print(f"   LSTM MAE (log-ret): {lstm_artifacts['metrics']['mae']:.4f}")
    
    # Quick test prediction
    print("\n🔮 Testing prediction on latest data...")
    preds = predict_14_day(xgb_artifacts, df)
    
    print(f"\n   Sample predictions (top 10 by change):")
    preds_sorted = preds.sort_values("predicted_change_pct", ascending=False).head(10)
    for _, row in preds_sorted.iterrows():
        direction = "📈" if row["predicted_change_pct"] > 0 else "📉"
        print(f"   {direction} {row['commodity']} @ {row['market']} ({row['district']}): "
              f"₹{row['modal_price']:.0f} → ₹{row['predicted_price_14d']:.0f} ({row['predicted_change_pct']:+.1f}%)")


if __name__ == "__main__":
    main()