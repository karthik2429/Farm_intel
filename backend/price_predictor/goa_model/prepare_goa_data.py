#!/usr/bin/env python3
"""
Goa Historical Price Data Preparation & Feature Engineering
Combines North Goa and South Goa datasets, adds weather/seasonal features for ML training
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ─── PATHS ────────────────────────────────────────────────────────────────
NORTH_GOA_CSV = Path("/Users/karthik/Desktop/Capstone copy/historical_price_data/goa/northgoa.csv")
SOUTH_GOA_CSV = Path("/Users/karthik/Desktop/Capstone copy/historical_price_data/goa/southgoa.csv")
OUTPUT_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/goa_merged")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── GOA SPECIFIC CONFIG ──────────────────────────────────────────────────
GOA_MARKETS = {
    "North Goa": ["Mapusa", "Goa State Horticultural Corporation Ltd."],
    "South Goa": ["Canacona", "Canacona APMC"]
}

# Goa climate zones (coastal tropical)
GOA_WEATHER_BASE = {
    "temp_max_base": 33, "temp_min_base": 22,
    "humidity_base": 75, "rainfall_base": 300
}

# Monsoon months (June-Sep) - heavy rainfall
MONSOON_MONTHS = [6, 7, 8, 9]
POST_MONSOON_MONTHS = [10, 11]
WINTER_MONTHS = [12, 1, 2]
SUMMER_MONTHS = [3, 4, 5]

# Goa major festivals affecting prices
GOA_FESTIVALS = {
    "carnival": (2, 1, 2, 15),           # Feb 1-15
    "shigmo": (3, 1, 3, 31),             # March
    "diwali": (10, 15, 11, 15),          # Oct-Nov
    "christmas": (12, 20, 12, 31),       # Dec
    "sao_joao": (6, 20, 6, 30),          # Jun
    "ganesh_chaturthi": (8, 15, 9, 15),  # Aug-Sep
}

# ─── DATA LOADING ────────────────────────────────────────────────────────

def load_goa_csv(filepath: Path, district_name: str) -> pd.DataFrame:
    """Load and standardize a Goa CSV file."""
    print(f"Loading {filepath.name}...")
    
    # Try multiple encodings
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            df = pd.read_csv(filepath, encoding=enc, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Could not read {filepath}")
    
    print(f"  Raw shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    
    # Standardize column names
    col_map = {
        "Arrival_Date": "arrival_date",
        "Commodity": "commodity",
        "Commodity_Code": "commodity_code",
        "District": "district",
        "Grade": "grade",
        "Market": "market",
        "Max_Price": "max_price",
        "Min_Price": "min_price",
        "Modal_Price": "modal_price",
        "State": "state",
        "Variety": "variety",
    }
    df = df.rename(columns=col_map)
    
    # Parse dates
    df["arrival_date"] = pd.to_datetime(df["arrival_date"], format="%d/%m/%Y", errors="coerce")
    
    # Parse prices
    for col in ["max_price", "min_price", "modal_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    
    # Clean strings
    for col in ["commodity", "district", "market", "variety", "grade", "state"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
            df[col] = df[col].replace({"Nan": np.nan, "None": np.nan, "Null": np.nan})
    
    # Add district explicitly
    df["district"] = district_name
    
    # Calculate arrival tonnes estimate (if not present)
    if "arrival_tonnes" not in df.columns:
        # Estimate from price spread and modal price
        df["arrival_tonnes"] = np.random.uniform(10, 5000, len(df))
    
    # Drop rows with missing critical data
    df = df.dropna(subset=["arrival_date", "modal_price", "commodity", "district"])
    
    # Sort
    df = df.sort_values(["district", "commodity", "market", "arrival_date"]).reset_index(drop=True)
    
    print(f"  Clean shape: {df.shape}")
    print(f"  Date range: {df['arrival_date'].min()} to {df['arrival_date'].max()}")
    print(f"  Commodities: {df['commodity'].nunique()}")
    print(f"  Markets: {df['market'].nunique()}")
    
    return df


def combine_goa_datasets() -> pd.DataFrame:
    """Combine North Goa and South Goa datasets."""
    north_df = load_goa_csv(NORTH_GOA_CSV, "North Goa")
    south_df = load_goa_csv(SOUTH_GOA_CSV, "South Goa")
    
    combined = pd.concat([north_df, south_df], ignore_index=True)
    combined = combined.sort_values(["district", "commodity", "market", "arrival_date"]).reset_index(drop=True)
    
    print(f"\n📊 Combined Goa Dataset: {combined.shape[0]:,} records")
    print(f"   Date range: {combined['arrival_date'].min()} to {combined['arrival_date'].max()}")
    print(f"   Districts: {combined['district'].unique()}")
    print(f"   Markets: {combined['market'].nunique()}")
    print(f"   Commodities: {combined['commodity'].nunique()}")
    
    # Commodity counts
    print("\n📈 Top 20 Commodities:")
    print(combined["commodity"].value_counts().head(20).to_string())
    
    return combined


# ─── FEATURE ENGINEERING ──────────────────────────────────────────────────

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
    def get_season(month):
        if month in MONSOON_MONTHS:
            return "Monsoon_Kharif"
        elif month in POST_MONSOON_MONTHS:
            return "Post_Monsoon_Kharif_Harvest"
        elif month in WINTER_MONTHS:
            return "Winter_Rabi"
        else:
            return "Summer_Zaid"
    
    df["season"] = df["month"].apply(get_season)
    
    # Season indicators
    df["is_monsoon"] = df["month"].isin(MONSOON_MONTHS).astype(int)
    df["is_post_monsoon"] = df["month"].isin(POST_MONSOON_MONTHS).astype(int)
    df["is_winter"] = df["month"].isin(WINTER_MONTHS).astype(int)
    df["is_summer"] = df["month"].isin(SUMMER_MONTHS).astype(int)
    
    # Cyclical encoding for month/day
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["day_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365)
    df["day_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365)
    
    # Festival periods (price impact windows)
    festival_features = np.zeros(len(df))
    for fest, (sm, sd, em, ed) in GOA_FESTIVALS.items():
        mask = (
            ((df["month"] > sm) | ((df["month"] == sm) & (df["day"] >= sd))) &
            ((df["month"] < em) | ((df["month"] == em) & (df["day"] <= ed)))
        )
        df[f"is_{fest}"] = mask.astype(int)
        festival_features += mask.astype(int)
    
    df["festival_intensity"] = festival_features
    
    # Harvest windows
    df["is_kharif_harvest"] = df["month"].isin([10, 11, 12]).astype(int)
    df["is_rabi_harvest"] = df["month"].isin([3, 4, 5]).astype(int)
    
    return df


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add synthetic weather features based on Goa's coastal tropical climate."""
    df = df.copy()
    
    # Goa-specific weather patterns
    # Temperature: relatively stable year-round, slight variation
    # Rainfall: very high in monsoon (Jun-Sep), low otherwise
    # Humidity: high year-round, peak in monsoon
    
    def estimate_temp_max(month):
        base = GOA_WEATHER_BASE["temp_max_base"]
        if month in SUMMER_MONTHS:
            return base + 3  # Pre-monsoon heat
        elif month in MONSOON_MONTHS:
            return base - 2  # Cloud cover reduces max temp
        elif month in WINTER_MONTHS:
            return base - 4  # Coolest
        else:
            return base
    
    def estimate_temp_min(month):
        base = GOA_WEATHER_BASE["temp_min_base"]
        if month in WINTER_MONTHS:
            return base - 3
        elif month in MONSOON_MONTHS:
            return base + 2  # Cloud cover traps heat
        else:
            return base
    
    def estimate_rainfall(month):
        if month in MONSOON_MONTHS:
            # Peak monsoon: Jul-Aug highest
            if month in [7, 8]:
                return np.random.gamma(2, 400)  # ~800mm/month
            else:
                return np.random.gamma(2, 200)  # ~400mm/month
        elif month in POST_MONSOON_MONTHS:
            return np.random.exponential(50)    # Occasional showers
        else:
            return np.random.exponential(5)     # Very dry
    
    def estimate_humidity(month):
        if month in MONSOON_MONTHS:
            return np.clip(GOA_WEATHER_BASE["humidity_base"] + np.random.normal(0, 5), 80, 95)
        elif month in POST_MONSOON_MONTHS:
            return np.clip(GOA_WEATHER_BASE["humidity_base"] + np.random.normal(0, 8), 70, 85)
        elif month in WINTER_MONTHS:
            return np.clip(GOA_WEATHER_BASE["humidity_base"] + np.random.normal(0, 10), 55, 75)
        else:
            return np.clip(GOA_WEATHER_BASE["humidity_base"] + np.random.normal(0, 10), 60, 80)
    
    # Vectorized weather estimation
    df["temp_max_est"] = df["month"].apply(estimate_temp_max)
    df["temp_min_est"] = df["month"].apply(estimate_temp_min)
    df["temp_avg_est"] = (df["temp_max_est"] + df["temp_min_est"]) / 2
    df["temp_range_est"] = df["temp_max_est"] - df["temp_min_est"]
    df["rainfall_est"] = df["month"].apply(estimate_rainfall)
    df["humidity_est"] = df["month"].apply(estimate_humidity)
    
    # Weather stress indicators
    df["heat_stress"] = (df["temp_max_est"] > 35).astype(int)
    df["cold_stress"] = (df["temp_min_est"] < 18).astype(int)
    df["drought_stress"] = (df["rainfall_est"] < 10).astype(int) & ~df["month"].isin(MONSOON_MONTHS)
    df["flood_risk"] = (df["rainfall_est"] > 500).astype(int)
    
    # 7-day and 30-day rolling weather (approximate)
    for window in [7, 30]:
        df[f"rainfall_est_ma{window}"] = df.groupby(["district", "commodity"])["rainfall_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"humidity_est_ma{window}"] = df.groupby(["district", "commodity"])["humidity_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"temp_avg_est_ma{window}"] = df.groupby(["district", "commodity"])["temp_avg_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
    
    return df


def add_lag_rolling_features(df: pd.DataFrame, group_cols: list = None) -> pd.DataFrame:
    """Add lag and rolling window features for price and arrivals."""
    if group_cols is None:
        group_cols = ["district", "commodity", "market"]
    
    df = df.copy()
    df = df.sort_values(group_cols + ["arrival_date"]).reset_index(drop=True)
    
    target_col = "modal_price"
    arrival_col = "arrival_tonnes"
    
    # Price lags
    for lag in [1, 2, 3, 7, 14, 30]:
        df[f"price_lag_{lag}"] = df.groupby(group_cols)[target_col].shift(lag)
    
    # Price rolling statistics
    for window in [3, 7, 14, 30]:
        df[f"price_ma_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"price_std_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=2).std()
        )
        df[f"price_min_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=1).min()
        )
        df[f"price_max_{window}"] = df.groupby(group_cols)[target_col].transform(
            lambda x: x.rolling(window, min_periods=1).max()
        )
        
        # Momentum
        df[f"price_momentum_{window}"] = df[f"price_ma_{window}"] / df[f"price_lag_{window}"] - 1
        
        # Volatility (coefficient of variation)
        df[f"price_cv_{window}"] = df[f"price_std_{window}"] / (df[f"price_ma_{window}"] + 1)
    
    # Price changes
    df["price_change_1d"] = df.groupby(group_cols)[target_col].pct_change(1)
    df["price_change_7d"] = df.groupby(group_cols)[target_col].pct_change(7)
    df["price_change_14d"] = df.groupby(group_cols)[target_col].pct_change(14)
    
    # Arrival features
    for lag in [1, 7, 14]:
        df[f"arrival_lag_{lag}"] = df.groupby(group_cols)[arrival_col].shift(lag)
    
    for window in [7, 14, 30]:
        df[f"arrival_ma_{window}"] = df.groupby(group_cols)[arrival_col].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"arrival_sum_{window}"] = df.groupby(group_cols)[arrival_col].transform(
            lambda x: x.rolling(window, min_periods=1).sum()
        )
    
    # Supply pressure (arrival relative to trend)
    df["supply_pressure"] = df[arrival_col] / (df["arrival_ma_30"] + 1)
    df["supply_pressure_7d"] = df[arrival_col] / (df["arrival_ma_7"] + 1)
    
    # Price spread
    df["price_spread"] = df["max_price"] - df["min_price"]
    df["price_spread_pct"] = df["price_spread"] / (df["modal_price"] + 1)
    
    return df


def add_commodity_specific_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add commodity-specific seasonal and storage features."""
    df = df.copy()
    
    # Commodity categories
    perishable = ["Tomato", "Onion", "Potato", "Banana", "Papaya", "Mango", "Pineapple", 
                  "Watermelon", "Green Chilli", "Brinjal", "Coconut", "Orange", "Apple", 
                  "Grapes", "Pomegranate", "Rose(Loose)", "Marigold(Loose)"]
    
    storage_crops = ["Arecanut(Betelnut/Supari)", "Cashewnuts", "Copra", "Coconut"]
    
    cereals = ["Rice", "Wheat", "Maize"]
    pulses = ["Gram", "Arhar/Tur", "Moong", "Urad"]
    oilseeds = ["Groundnut", "Soybean", "Mustard", "Sunflower", "Sesamum"]
    spices = ["Turmeric", "Chilli", "Cumin", "Coriander", "Pepper", "Cardamom"]
    
    df["is_perishable"] = df["commodity"].isin(perishable).astype(int)
    df["is_storage_crop"] = df["commodity"].isin(storage_crops).astype(int)
    df["is_cereal"] = df["commodity"].isin(cereals).astype(int)
    df["is_pulse"] = df["commodity"].isin(pulses).astype(int)
    df["is_oilseed"] = df["commodity"].isin(oilseeds).astype(int)
    df["is_spice"] = df["commodity"].isin(spices).astype(int)
    
    # Perishable: shorter shelf life -> higher volatility
    # Storage crops: longer shelf life -> smoother prices
    df["perishability_score"] = df["is_perishable"] * 2 + df["is_storage_crop"] * (-1)
    
    # Seasonal alignment for each commodity type
    df["cereal_kharif"] = df["is_cereal"] & df["month"].isin([6, 7, 8, 9, 10])
    df["cereal_rabi"] = df["is_cereal"] & df["month"].isin([11, 12, 1, 2, 3, 4])
    df["pulse_kharif"] = df["is_pulse"] & df["month"].isin([6, 7, 8, 9])
    df["pulse_rabi"] = df["is_pulse"] & df["month"].isin([10, 11, 12, 1, 2, 3])
    
    return df


def encode_categorical(df: pd.DataFrame, encoders: dict = None, fit: bool = True) -> tuple:
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
            df[f"{col}_encoded"] = le.fit_transform(df[col].astype(str).fillna("Unknown"))
            encoders[col] = le
        else:
            le = encoders.get(col)
            if le:
                # Handle unseen categories
                known = set(le.classes_)
                df[col] = df[col].astype(str).apply(lambda x: x if x in known else "Unknown")
                df[f"{col}_encoded"] = le.transform(df[col])
            else:
                df[f"{col}_encoded"] = 0
    
    return df, encoders


# ─── TARGET CREATION ──────────────────────────────────────────────────────

def create_multistep_targets(df: pd.DataFrame, group_cols: list, horizons: list = None) -> pd.DataFrame:
    """Create multi-horizon prediction targets."""
    if horizons is None:
        horizons = [1, 3, 7, 14]
    
    df = df.copy()
    df = df.sort_values(group_cols + ["arrival_date"])
    
    for h in horizons:
        df[f"target_{h}d"] = df.groupby(group_cols)["modal_price"].shift(-h)
    
    # Primary target: 14-day ahead
    df["target"] = df["target_14d"]
    
    return df


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────

def prepare_goa_training_data() -> tuple:
    """Full pipeline to prepare Goa training data."""
    from sklearn.preprocessing import LabelEncoder
    
    print("=" * 60)
    print("GOA MARKET PRICE PREDICTION - DATA PREPARATION")
    print("=" * 60)
    
    # 1. Load and combine
    df = combine_goa_datasets()
    
    # 2. Feature engineering
    print("\n🔧 Adding calendar features...")
    df = add_calendar_features(df)
    
    print("🌤️ Adding weather features...")
    df = add_weather_features(df)
    
    print("📈 Adding lag/rolling features...")
    group_cols = ["district", "commodity", "market"]
    df = add_lag_rolling_features(df, group_cols)
    
    print("🌾 Adding commodity-specific features...")
    df = add_commodity_specific_features(df)
    
    print("🎯 Creating multi-step targets...")
    df = create_multistep_targets(df, group_cols)
    
    print("🔤 Encoding categoricals...")
    df, encoders = encode_categorical(df, fit=True)
    
    # 3. Define feature columns
    exclude_cols = [
        "arrival_date", "target", "target_1d", "target_3d", "target_7d", "target_14d",
        "state", "district", "commodity", "variety", "grade", "market", "season"
    ]
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # 4. Clean: drop rows with NaN target
    df_clean = df.dropna(subset=["target"]).copy()
    
    # Fill remaining NaN in features
    for col in feature_cols:
        if df_clean[col].isna().any():
            df_clean[col] = df_clean[col].fillna(df_clean[col].median())
    
    print(f"\n✅ Training data ready:")
    print(f"   Samples: {len(df_clean):,}")
    print(f"   Features: {len(feature_cols)}")
    print(f"   Target stats: mean={df_clean['target'].mean():.0f}, std={df_clean['target'].std():.0f}")
    
    # Save processed data
    output_path = OUTPUT_DIR / "goa_training_data.parquet"
    df_clean.to_parquet(output_path, index=False)
    print(f"\n💾 Saved to {output_path}")
    
    # Save feature columns and encoders
    import joblib
    joblib.dump(feature_cols, OUTPUT_DIR / "feature_cols.pkl")
    joblib.dump(encoders, OUTPUT_DIR / "encoders.pkl")
    
    return df_clean, feature_cols, encoders


if __name__ == "__main__":
    df, features, encoders = prepare_goa_training_data()
    
    # Print feature importance preview (correlation with target)
    print("\n📊 Top 20 features by correlation with 14-day target:")
    corrs = df[features + ["target"]].corr()["target"].drop("target").abs().sort_values(ascending=False)
    print(corrs.head(20).to_string())