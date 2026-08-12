"""
Feature Engineering & Model Training for 14-Day Price Prediction
"""

import pandas as pd
import numpy as np
from pathlib import Path
import joblib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings("ignore")

# ML imports
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
import xgboost as xgb

DATA_DIR = Path(__file__).parent.parent / "data" / "historical_prices"
MODEL_DIR = Path(__file__).parent.parent / "models" / "price_predictor"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def load_master_data() -> pd.DataFrame:
    """Load the master historical price dataset."""
    path = DATA_DIR / "master_historical_prices.csv"
    if not path.exists():
        raise FileNotFoundError(f"Master data not found at {path}. Run download_historical.py first.")
    
    df = pd.read_csv(path, parse_dates=["arrival_date"])
    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar/seasonal features."""
    df = df.copy()
    df["year"] = df["arrival_date"].dt.year
    df["month"] = df["arrival_date"].dt.month
    df["day_of_month"] = df["arrival_date"].dt.day
    df["day_of_week"] = df["arrival_date"].dt.dayofweek
    df["week_of_year"] = df["arrival_date"].dt.isocalendar().week
    df["quarter"] = df["arrival_date"].dt.quarter
    
    # Indian agricultural seasons
    def get_season(month):
        if month in [6, 7, 8, 9, 10]:
            return "Kharif"
        elif month in [11, 12, 1, 2, 3]:
            return "Rabi"
        else:
            return "Zaid"
    
    df["season"] = df["month"].apply(get_season)
    
    # Festival indicators (major price impact periods)
    df["is_diwali"] = ((df["month"] == 10) | (df["month"] == 11)) & (df["day_of_month"] <= 15)
    df["is_holi"] = (df["month"] == 3) & (df["day_of_month"] >= 15)
    df["is_onsam_rakhi"] = (df["month"] == 8) & (df["day_of_month"] >= 15)
    df["is_pongal"] = (df["month"] == 1) & (df["day_of_month"] <= 15)
    df["is_baisakhi"] = (df["month"] == 4) & (df["day_of_month"] <= 15)
    
    # Harvest windows (major supply influx -> price drop)
    df["is_kharif_harvest"] = df["month"].isin([10, 11, 12])
    df["is_rabi_harvest"] = df["month"].isin([3, 4, 5])
    
    return df


def add_lag_features(df: pd.DataFrame, group_cols: List[str], target_col: str = "modal_price", 
                     lags: List[int] = None, windows: List[int] = None) -> pd.DataFrame:
    """Add lag and rolling window features grouped by commodity+market."""
    if lags is None:
        lags = [1, 2, 3, 7, 14, 30]
    if windows is None:
        windows = [7, 14, 30]
    
    df = df.copy()
    df = df.sort_values(group_cols + ["arrival_date"])
    
    for lag in lags:
        df[f"price_lag_{lag}"] = df.groupby(group_cols)[target_col].shift(lag)
    
    for window in windows:
        df[f"price_rolling_mean_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"price_rolling_std_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=2).std()
        )
        df[f"price_rolling_min_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=1).min()
        )
        df[f"price_rolling_max_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=1).max()
        )
        
        # Momentum features
        df[f"price_momentum_{window}"] = df[f"price_rolling_mean_{window}"] / df[f"price_lag_{window}"] - 1
        
        # Volatility
        df[f"price_volatility_{window}"] = df[f"price_rolling_std_{window}"] / df[f"price_rolling_mean_{window}"]
    
    # Price change features
    df["price_change_1d"] = df.groupby(group_cols)[target_col].pct_change(1)
    df["price_change_7d"] = df.groupby(group_cols)[target_col].pct_change(7)
    
    return df


def add_arrival_features(df: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    """Add arrival volume features."""
    df = df.copy()
    
    # Arrival lags and rolling
    for lag in [1, 7, 14]:
        df[f"arrival_lag_{lag}"] = df.groupby(group_cols)["arrival_tonnes"].shift(lag)
    
    for window in [7, 14, 30]:
        df[f"arrival_rolling_mean_{window}"] = df.groupby(group_cols)["arrival_tonnes"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"arrival_rolling_sum_{window}"] = df.groupby(group_cols)["arrival_tonnes"].transform(
            lambda x: x.rolling(window, min_periods=1).sum()
        )
    
    # Supply pressure indicator
    df["supply_pressure"] = df["arrival_tonnes"] / (df["arrival_rolling_mean_30"] + 1)
    
    return df


def add_weather_features(df: pd.DataFrame, weather_cache: Dict = None) -> pd.DataFrame:
    """
    Add weather features. In production, this fetches from Open-Meteo ERA5 historical.
    For training, we use a cached mapping or synthetic patterns.
    """
    df = df.copy()
    
    # For now, add synthetic weather patterns based on season/location
    # In production: fetch real ERA5 data per district
    
    # Temperature seasonal patterns (approximate for Indian states)
    state_temp_base = {
        "Maharashtra": {"max": 35, "min": 20},
        "Karnataka": {"max": 32, "min": 18},
        "Punjab": {"max": 38, "min": 15},
        "Madhya Pradesh": {"max": 37, "min": 18},
        "Andhra Pradesh": {"max": 36, "min": 22},
    }
    
    def get_seasonal_temp(state, month, is_max=True):
        base = state_temp_base.get(state, {"max": 33, "min": 20})
        key = "max" if is_max else "min"
        # Seasonal variation
        if month in [4, 5, 6]:  # Summer
            return base[key] + 5
        elif month in [12, 1, 2]:  # Winter
            return base[key] - 5
        else:  # Monsoon/Post-monsoon
            return base[key]
    
    df["temp_max_est"] = df.apply(lambda r: get_seasonal_temp(r["state"], r["month"], True), axis=1)
    df["temp_min_est"] = df.apply(lambda r: get_seasonal_temp(r["state"], r["month"], False), axis=1)
    
    # Rainfall estimate by season
    monsoon_months = [6, 7, 8, 9]
    df["rainfall_est"] = df["month"].apply(lambda m: np.random.gamma(2, 50) if m in monsoon_months else np.random.exponential(5))
    
    # Humidity
    df["humidity_est"] = df["month"].apply(lambda m: 85 if m in monsoon_months else 60)
    
    return df


def encode_categorical_features(df: pd.DataFrame, encoders: Dict = None, fit: bool = True) -> Tuple[pd.DataFrame, Dict]:
    """Encode categorical features."""
    df = df.copy()
    cat_cols = ["state", "district", "commodity", "variety", "grade", "season"]
    
    if encoders is None:
        encoders = {}
    
    for col in cat_cols:
        if col not in df.columns:
            continue
        
        if fit:
            le = LabelEncoder()
            df[f"{col}_encoded"] = le.fit_transform(df[col].astype(str).fillna("Unknown"))
            encoders[col] = le
        else:
            le = encoders.get(col)
            if le:
                # Handle unseen categories
                known_classes = set(le.classes_)
                df[col] = df[col].astype(str).apply(lambda x: x if x in known_classes else "Unknown")
                df[f"{col}_encoded"] = le.transform(df[col])
            else:
                df[f"{col}_encoded"] = 0
    
    return df, encoders


def create_training_dataset(df: pd.DataFrame, target_horizon: int = 14) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Create supervised learning dataset for multi-step price prediction.
    Target: modal_price at t+14 (14 days ahead)
    """
    group_cols = ["state", "district", "commodity"]
    
    print("🔧 Engineering features...")
    df = add_calendar_features(df)
    df = add_lag_features(df, group_cols)
    df = add_arrival_features(df, group_cols)
    df = add_weather_features(df)
    df, encoders = encode_categorical_features(df, fit=True)
    
    # Target: price 14 days ahead
    df = df.sort_values(group_cols + ["arrival_date"])
    df["target_price_14d"] = df.groupby(group_cols)["modal_price"].shift(-target_horizon)
    
    # Also create multi-horizon targets for 1, 7, 14 days
    for h in [1, 7, 14]:
        df[f"target_price_{h}d"] = df.groupby(group_cols)["modal_price"].shift(-h)
    
    # Drop rows with NaN target
    feature_cols = [c for c in df.columns if c not in [
        "arrival_date", "target_price_14d", "target_price_1d", "target_price_7d",
        "state", "district", "commodity", "variety", "grade", "season", "market"
    ]]
    
    # Remove rows where any target is NaN
    df_clean = df.dropna(subset=["target_price_14d"])
    
    X = df_clean[feature_cols]
    y = df_clean["target_price_14d"]
    
    print(f"✅ Training dataset: {X.shape[0]:,} samples, {X.shape[1]} features")
    print(f"   Target stats: mean={y.mean():.0f}, std={y.std():.0f}, min={y.min():.0f}, max={y.max():.0f}")
    
    return X, y, feature_cols, encoders


def train_price_model(X: pd.DataFrame, y: pd.Series, feature_cols: List[str], 
                      encoders: Dict, params: Dict = None) -> Dict:
    """Train XGBoost model for price prediction."""
    
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
    
    # Time series split (last 20% as test)
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
    mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100
    
    print(f"\n📈 Model Performance:")
    print(f"   MAE:  ₹{mae:.2f}")
    print(f"   RMSE: ₹{rmse:.2f}")
    print(f"   R²:   {r2:.4f}")
    print(f"   MAPE: {mape:.2f}%")
    
    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)
    
    print(f"\n🔝 Top 15 Features:")
    for _, row in importance.head(15).iterrows():
        print(f"   {row['feature']}: {row['importance']:.4f}")
    
    # Save model artifacts
    artifacts = {
        "model": model,
        "feature_cols": feature_cols,
        "encoders": encoders,
        "params": params,
        "metrics": {
            "mae": float(mae),
            "rmse": float(rmse),
            "r2": float(r2),
            "mape": float(mape)
        },
        "feature_importance": importance.to_dict("records"),
        "trained_at": datetime.now().isoformat(),
        "n_samples": int(len(X_train))
    }
    
    joblib.dump(artifacts, MODEL_DIR / "price_model.pkl")
    print(f"\n💾 Model saved to {MODEL_DIR / 'price_model.pkl'}")
    
    return artifacts


def predict_14_day(model_artifacts: Dict, df_latest: pd.DataFrame, 
                   weather_forecast: pd.DataFrame = None) -> pd.DataFrame:
    """
    Generate 14-day price predictions for given latest data.
    """
    model = model_artifacts["model"]
    feature_cols = model_artifacts["feature_cols"]
    encoders = model_artifacts["encoders"]
    
    # Prepare features (same pipeline as training)
    group_cols = ["state", "district", "commodity"]
    df = add_calendar_features(df_latest)
    df = add_lag_features(df, group_cols)
    df = add_arrival_features(df, group_cols)
    df = add_weather_features(df, weather_forecast)
    df, _ = encode_categorical_features(df, encoders, fit=False)
    
    # Get latest row per group
    df_latest_row = df.sort_values("arrival_date").groupby(group_cols).tail(1)
    
    # Ensure all feature columns present
    for col in feature_cols:
        if col not in df_latest_row.columns:
            df_latest_row[col] = 0
    
    X_pred = df_latest_row[feature_cols]
    
    # Predict
    pred_14d = model.predict(X_pred)
    
    results = df_latest_row[group_cols + ["arrival_date", "modal_price"]].copy()
    results["predicted_price_14d"] = pred_14d
    results["prediction_date"] = datetime.now().date()
    
    # For full 14-day trajectory, we'd iterate (simplified here)
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Price Prediction Model Training")
    print("=" * 60)
    
    # Load data
    df = load_master_data()
    print(f"Loaded {len(df):,} records from {df['arrival_date'].min()} to {df['arrival_date'].max()}")
    
    # Create training dataset
    X, y, feature_cols, encoders = create_training_dataset(df, target_horizon=14)
    
    # Train model
    artifacts = train_price_model(X, y, feature_cols, encoders)
    
    print("\n✅ Training complete!")
    print(f"   Model: {MODEL_DIR / 'price_model.pkl'}")
    print(f"   Metrics: MAE=₹{artifacts['metrics']['mae']:.0f}, R²={artifacts['metrics']['r2']:.3f}")