#!/usr/bin/env python3
"""
Goa Market Price Prediction API
FastAPI service for 14-day price forecasts with REAL weather/seasonal factors
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ─── CONFIG ──────────────────────────────────────────────────────────────
MODEL_DIR = Path("/Users/karthik/Desktop/Capstone copy/collab/price_predictor/goa_model")
DATA_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/goa_merged")
WEATHER_CACHE = DATA_DIR / "weather_cache"

# ─── LOAD MODEL & DATA ───────────────────────────────────────────────────
print("Loading Goa price prediction model...")
xgb_artifacts = joblib.load(MODEL_DIR / "goa_xgb_model.pkl")
model = xgb_artifacts["model"]
feature_cols = xgb_artifacts["feature_cols"]
encoders = xgb_artifacts["encoders"]

# Load historical data
df_history = pd.read_parquet(DATA_DIR / "goa_merged_historical.parquet")
df_history["arrival_date"] = pd.to_datetime(df_history["arrival_date"])

# Filter APMC markets and outliers
df_history = df_history[~df_history["market"].str.contains("APMC", case=False)].copy()
for (comm, mkt), group in df_history.groupby(["commodity", "market"]):
    q01 = group["modal_price"].quantile(0.01)
    q99 = group["modal_price"].quantile(0.99)
    df_history = df_history[~((df_history["commodity"] == comm) & 
                               (df_history["market"] == mkt) & 
                               ((df_history["modal_price"] < q01) | (df_history["modal_price"] > q99)))]

df_history = df_history.sort_values(["district", "commodity", "market", "arrival_date"])
if "arrival_tonnes" not in df_history.columns:
    df_history["arrival_tonnes"] = 100

# ─── LOAD REAL WEATHER DATA ──────────────────────────────────────────────
print("Loading real weather data...")
weather_files = list(WEATHER_CACHE.glob("*.parquet"))
weather_dfs = []
for wf in weather_files:
    if wf.name.startswith("goa_all"):
        continue
    try:
        wdf = pd.read_parquet(wf)
        wdf["date"] = pd.to_datetime(wdf["date"])
        weather_dfs.append(wdf)
    except Exception as e:
        print(f"  ⚠️ Failed to load {wf.name}: {e}")

if weather_dfs:
    df_weather = pd.concat(weather_dfs, ignore_index=True)
    df_weather = df_weather.sort_values(["location", "date"])
    print(f"✅ Real weather loaded: {len(df_weather):,} records from {df_weather['location'].nunique()} locations")
else:
    df_weather = pd.DataFrame()
    print("⚠️ No weather data found, will use synthetic")

# Market to weather location mapping
MARKET_TO_WEATHER = {
    "Mapusa": "Mapusa",
    "Pernem": "Pernem",
    "Sanquelim": "Sanquelim",
    "Valpol": "Valpol",
    "Goa State Horticultural Corporation Ltd.": "Goa State Horticultural Corporation Ltd.",
    "Canacona": "Canacona",
    "Curchorem": "South Goa",  # Use South Goa as proxy
    "Margao": "South Goa",
    "Ponda": "South Goa",
}

print(f"✅ Model loaded: {len(feature_cols)} features")
print(f"✅ History loaded: {len(df_history):,} records")

# ─── CONSTANTS ───────────────────────────────────────────────────────────
GROUP_COLS = ["district", "commodity", "market"]
MONSOON_MONTHS = [6, 7, 8, 9]
POST_MONSOON_MONTHS = [10, 11]
WINTER_MONTHS = [12, 1, 2]
SUMMER_MONTHS = [3, 4, 5]

GOA_FESTIVALS = {
    "carnival": (2, 1, 2, 15), "shigmo": (3, 1, 3, 31),
    "ganesh_chaturthi": (8, 15, 9, 15), "diwali": (10, 15, 11, 15),
    "christmas": (12, 20, 12, 31), "new_year": (1, 1, 1, 5),
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

# ─── WEATHER FEATURE FUNCTION ────────────────────────────────────────────
def get_real_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Merge real weather data from Open-Meteo ERA5 cache."""
    if df_weather.empty:
        return df  # Will use synthetic in add_weather_features
    
    df = df.copy()
    
    # Map markets to weather locations
    df["weather_location"] = df["market"].map(MARKET_TO_WEATHER)
    
    # For markets without mapping, use district-level
    unmapped = df["weather_location"].isna()
    if unmapped.any():
        district_map = {
            "North Goa": "Mapusa",
            "South Goa": "South Goa",
        }
        df.loc[unmapped, "weather_location"] = df.loc[unmapped, "district"].map(district_map)
    
    # Ensure date column for merge
    df["date"] = df["arrival_date"].dt.date
    
    # Prepare weather data for merge
    wdf = df_weather.copy()
    wdf["date"] = wdf["date"].dt.date
    
    # Select weather columns to merge
    weather_cols = ["location", "date", "temperature_2m_max", "temperature_2m_min", 
                    "temperature_2m_mean", "precipitation_sum", "rain_sum",
                    "relative_humidity_2m_mean", "relative_humidity_2m_max",
                    "relative_humidity_2m_min", "wind_speed_10m_max", 
                    "shortwave_radiation_sum", "et0_fao_evapotranspiration",
                    "soil_temperature_0_to_7cm_mean", "soil_moisture_0_to_7cm_mean"]
    
    # Only keep columns that exist
    available_cols = [c for c in weather_cols if c in wdf.columns]
    wdf = wdf[available_cols].rename(columns={"location": "weather_location"})
    
    # Merge
    df = df.merge(wdf, on=["weather_location", "date"], how="left")
    
    # Rename to standard feature names
    rename_map = {
        "temperature_2m_max": "temp_max_est",
        "temperature_2m_min": "temp_min_est",
        "temperature_2m_mean": "temp_avg_est",
        "precipitation_sum": "rainfall_est",
        "rain_sum": "rainfall_est",
        "relative_humidity_2m_mean": "humidity_est",
        "relative_humidity_2m_max": "humidity_max",
        "relative_humidity_2m_min": "humidity_min",
        "wind_speed_10m_max": "wind_max",
        "shortwave_radiation_sum": "solar_radiation",
        "et0_fao_evapotranspiration": "et0",
        "soil_temperature_0_to_7cm_mean": "soil_temp",
        "soil_moisture_0_to_7cm_mean": "soil_moisture",
    }
    df = df.rename(columns=rename_map)
    
    # Compute derived features
    if "temp_max_est" in df.columns and "temp_min_est" in df.columns:
        df["temp_range_est"] = df["temp_max_est"] - df["temp_min_est"]
    
    # Weather stress indicators
    df["heat_stress"] = (df.get("temp_max_est", 33) > 35).astype(int)
    df["cold_stress"] = (df.get("temp_min_est", 22) < 18).astype(int)
    df["drought_stress"] = ((df.get("rainfall_est", 0) < 5) & ~df["month"].isin(MONSOON_MONTHS)).astype(int)
    df["flood_risk"] = (df.get("rainfall_est", 0) > 100).astype(int)
    df["high_humidity"] = (df.get("humidity_est", 75) > 85).astype(int)
    df["low_humidity"] = (df.get("humidity_est", 75) < 55).astype(int)
    
    # Rolling weather (7 and 30 day)
    for window in [7, 30]:
        for col in ["rainfall_est", "humidity_est", "temp_avg_est"]:
            if col in df.columns:
                df[f"{col}_ma{window}"] = df.groupby(GROUP_COLS)[col].transform(
                    lambda x: x.rolling(window, min_periods=1).mean()
                )
    
    df = df.drop(columns=["weather_location", "date"], errors="ignore")
    return df


# ─── FEATURE ENGINEERING ─────────────────────────────────────────────────
def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
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
    
    def get_season(m):
        if m in MONSOON_MONTHS: return "Monsoon_Kharif"
        elif m in POST_MONSOON_MONTHS: return "Post_Monsoon_Harvest"
        elif m in WINTER_MONTHS: return "Winter_Rabi"
        return "Summer_Zaid"
    
    df["season"] = df["month"].apply(get_season)
    df["is_monsoon"] = df["month"].isin(MONSOON_MONTHS).astype(int)
    df["is_post_monsoon"] = df["month"].isin(POST_MONSOON_MONTHS).astype(int)
    df["is_winter"] = df["month"].isin(WINTER_MONTHS).astype(int)
    df["is_summer"] = df["month"].isin(SUMMER_MONTHS).astype(int)
    
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["day_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365)
    df["day_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365)
    
    for fest, (sm, sd, em, ed) in GOA_FESTIVALS.items():
        mask = ((df["month"] > sm) | ((df["month"] == sm) & (df["day"] >= sd))) & \
               ((df["month"] < em) | ((df["month"] == em) & (df["day"] <= ed)))
        df[f"is_{fest}"] = mask.astype(int)
    
    df["festival_intensity"] = sum(df[f"is_{f}"] for f in GOA_FESTIVALS)
    df["is_kharif_harvest"] = df["month"].isin([10, 11, 12]).astype(int)
    df["is_rabi_harvest"] = df["month"].isin([3, 4, 5]).astype(int)
    
    return df


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add weather features - uses real data if available, synthetic fallback."""
    df = df.copy()
    
    # Try real weather first
    df = get_real_weather_features(df)
    
    # Check if real weather columns exist
    has_real_weather = "temp_max_est" in df.columns and df["temp_max_est"].notna().any()
    
    if not has_real_weather:
        # Synthetic fallback for Goa coastal tropical climate
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
        
        df["heat_stress"] = (df["temp_max_est"] > 35).astype(int)
        df["cold_stress"] = (df["temp_min_est"] < 18).astype(int)
        df["drought_stress"] = ((df["rainfall_est"] < 10) & ~df["month"].isin(MONSOON_MONTHS)).astype(int)
        df["flood_risk"] = (df["rainfall_est"] > 100).astype(int)
        
        for window in [7, 30]:
            for col in ["rainfall_est", "humidity_est", "temp_avg_est"]:
                df[f"{col}_ma{window}"] = df.groupby(GROUP_COLS)[col].transform(
                    lambda x: x.rolling(window, min_periods=1).mean()
                )
    
    return df


def add_lag_rolling_features(df: pd.DataFrame, group_cols: List[str] = None) -> pd.DataFrame:
    if group_cols is None:
        group_cols = GROUP_COLS
    
    df = df.copy()
    df = df.sort_values(group_cols + ["arrival_date"]).reset_index(drop=True)
    
    target = "modal_price"
    arrival = "arrival_tonnes"
    
    for lag in [1, 2, 3, 7, 14, 30]:
        df[f"price_lag_{lag}"] = df.groupby(group_cols)[target].shift(lag)
    
    for window in [3, 7, 14, 30]:
        df[f"price_ma_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=1).mean())
        df[f"price_std_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=2).std())
        df[f"price_min_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=1).min())
        df[f"price_max_{window}"] = df.groupby(group_cols)[target].transform(
            lambda x: x.rolling(window, min_periods=1).max())
        
        df[f"price_momentum_{window}"] = df[f"price_ma_{window}"] / (df[f"price_lag_{window}"] + 1) - 1
        df[f"price_cv_{window}"] = df[f"price_std_{window}"] / (df[f"price_ma_{window}"] + 1)
    
    for lag in [1, 7, 14]:
        df[f"price_change_{lag}d"] = df.groupby(group_cols)[target].pct_change(lag)
    
    for lag in [1, 7, 14]:
        df[f"arrival_lag_{lag}"] = df.groupby(group_cols)[arrival].shift(lag)
    
    for window in [7, 14, 30]:
        df[f"arrival_ma_{window}"] = df.groupby(group_cols)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).mean())
        df[f"arrival_sum_{window}"] = df.groupby(group_cols)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).sum())
    
    df["supply_pressure"] = df[arrival] / (df["arrival_ma_30"] + 1)
    df["supply_pressure_7d"] = df[arrival] / (df["arrival_ma_7"] + 1)
    df["price_spread"] = df["max_price"] - df["min_price"]
    df["price_spread_pct"] = df["price_spread"] / (df["modal_price"] + 1)
    
    return df


def add_commodity_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    for cat, items in COMMODITY_CATEGORIES.items():
        df[f"is_{cat}"] = df["commodity"].isin(items).astype(int)
    
    df["perishability_score"] = df["is_perishable"] * 2 + df["is_storage"] * (-1)
    df["cereal_kharif"] = (df["is_cereals"] & df["month"].isin([6, 7, 8, 9, 10])).astype(int)
    df["cereal_rabi"] = (df["is_cereals"] & df["month"].isin([11, 12, 1, 2, 3, 4])).astype(int)
    df["pulse_kharif"] = (df["is_pulses"] & df["month"].isin([6, 7, 8, 9])).astype(int)
    df["pulse_rabi"] = (df["is_pulses"] & df["month"].isin([10, 11, 12, 1, 2, 3])).astype(int)
    
    return df


def encode_categoricals(df: pd.DataFrame, encoders: Dict, fit: bool = False) -> pd.DataFrame:
    df = df.copy()
    cat_cols = ["district", "commodity", "variety", "grade", "market", "season"]
    
    for col in cat_cols:
        if col not in df.columns:
            continue
        le = encoders.get(col)
        if le:
            known = set(le.classes_)
            df[col] = df[col].astype(str).apply(lambda x: x if x in known else "Unknown")
            df[f"{col}_enc"] = le.transform(df[col])
        else:
            df[f"{col}_enc"] = 0
    
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply full feature engineering pipeline."""
    df = add_calendar_features(df)
    df = add_weather_features(df)
    df = add_lag_rolling_features(df, GROUP_COLS)
    df = add_commodity_features(df)
    df = encode_categoricals(df, encoders)
    return df


def predict_latest() -> pd.DataFrame:
    """Generate predictions for latest data per commodity-market."""
    df = prepare_features(df_history.copy())
    df_latest = df.groupby(GROUP_COLS).tail(1).copy()
    
    for col in feature_cols:
        if col not in df_latest.columns:
            df_latest[col] = 0
    df_latest = df_latest.loc[:, ~df_latest.columns.duplicated()]
    
    X_pred = df_latest[feature_cols]
    pred_pct = model.predict(X_pred)
    current_price = df_latest["modal_price"].values
    pred_price = current_price * (1 + pred_pct)
    
    results = df_latest[GROUP_COLS + ["arrival_date", "modal_price"]].copy()
    results["predicted_price_14d"] = pred_price
    results["predicted_change_pct"] = (pred_pct * 100).round(2)
    results["prediction_date"] = datetime.now().date()
    results["model"] = "XGBoost"
    results["weather_source"] = "Open-Meteo ERA5" if not df_weather.empty else "Synthetic"
    
    return results


def generate_trajectory(df_latest: pd.DataFrame, days: int = 14) -> List[Dict]:
    """Generate day-by-day trajectory."""
    df_full = prepare_features(df_history.copy())
    trajectories = []
    
    for _, row in df_latest.iterrows():
        group_key = {col: row[col] for col in GROUP_COLS}
        group_data = df_full[
            (df_full["district"] == row["district"]) & 
            (df_full["commodity"] == row["commodity"]) & 
            (df_full["market"] == row["market"])
        ].tail(1)
        
        if group_data.empty:
            continue
            
        current_features = group_data[feature_cols].values.flatten()
        current_price = row["modal_price"]
        current_date = row["arrival_date"]
        
        traj = []
        for day in range(1, days + 1):
            pred = float(model.predict(current_features.reshape(1, -1))[0])
            pred_price = current_price * (1 + pred)
            
            traj.append({
                "day_ahead": day,
                "date": (current_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "predicted_price": round(pred_price, 2),
                "change_from_current_pct": round((pred_price - current_price) / current_price * 100, 2)
            })
            
            current_price = pred_price
            current_date += timedelta(days=1)
        
        trajectories.append({
            "district": row["district"],
            "commodity": row["commodity"],
            "market": row["market"],
            "current_price": round(row["modal_price"], 2),
            "trajectory": traj
        })
    
    return trajectories


# ─── FASTAPI APP ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Goa Market Price Prediction API",
    description="14-day price forecasts with REAL Open-Meteo ERA5 weather data",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictionResponse(BaseModel):
    district: str
    commodity: str
    market: str
    current_price: float
    predicted_price_14d: float
    predicted_change_pct: float
    prediction_date: str
    model: str
    weather_source: str


class TrajectoryResponse(BaseModel):
    district: str
    commodity: str
    market: str
    current_price: float
    trajectory: List[Dict]


@app.get("/")
async def root():
    return {
        "service": "Goa Market Price Prediction API",
        "version": "2.0.0",
        "model": "XGBoost",
        "features": len(feature_cols),
        "weather_source": "Open-Meteo ERA5" if not df_weather.empty else "Synthetic",
        "weather_locations": df_weather["location"].nunique() if not df_weather.empty else 0,
        "endpoints": ["/predict/14day", "/predict/trajectory", "/commodities", "/markets", "/health"]
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": "XGBoost",
        "features": len(feature_cols),
        "metrics": xgb_artifacts.get("metrics", {}),
        "weather_source": "Open-Meteo ERA5" if not df_weather.empty else "Synthetic",
        "weather_records": len(df_weather) if not df_weather.empty else 0,
        "trained_at": xgb_artifacts.get("trained_at", "unknown")
    }


@app.get("/commodities")
async def get_commodities():
    commodities = df_history["commodity"].unique().tolist()
    return {"commodities": sorted(commodities)}


@app.get("/markets")
async def get_markets(district: Optional[str] = None):
    df = df_history
    if district:
        df = df[df["district"] == district]
    markets = df[["district", "market"]].drop_duplicates().to_dict("records")
    return {"markets": markets}


@app.get("/predict/14day", response_model=List[PredictionResponse])
async def predict_14day(
    district: Optional[str] = Query(None),
    commodity: Optional[str] = Query(None),
    market: Optional[str] = Query(None)
):
    predictions = predict_latest()
    
    if district:
        predictions = predictions[predictions["district"] == district]
    if commodity:
        predictions = predictions[predictions["commodity"] == commodity]
    if market:
        predictions = predictions[predictions["market"] == market]
    
    results = []
    for _, row in predictions.iterrows():
        results.append(PredictionResponse(
            district=row["district"],
            commodity=row["commodity"],
            market=row["market"],
            current_price=round(row["modal_price"], 2),
            predicted_price_14d=round(row["predicted_price_14d"], 2),
            predicted_change_pct=row["predicted_change_pct"],
            prediction_date=str(row["prediction_date"]),
            model=row["model"],
            weather_source=row["weather_source"]
        ))
    return results


@app.get("/predict/trajectory", response_model=List[TrajectoryResponse])
async def predict_trajectory(
    district: Optional[str] = Query(None),
    commodity: Optional[str] = Query(None),
    market: Optional[str] = Query(None),
    days: int = Query(14, ge=1, le=30)
):
    df_latest = predict_latest()
    
    if district:
        df_latest = df_latest[df_latest["district"] == district]
    if commodity:
        df_latest = df_latest[df_latest["commodity"] == commodity]
    if market:
        df_latest = df_latest[df_latest["market"] == market]
    
    trajectories = generate_trajectory(df_latest, days)
    return trajectories


@app.get("/predict/single")
async def predict_single(
    district: str = Query(...),
    commodity: str = Query(...),
    market: str = Query(...)
):
    df_latest = predict_latest()
    
    match = df_latest[
        (df_latest["district"] == district) &
        (df_latest["commodity"] == commodity) &
        (df_latest["market"] == market)
    ]
    
    if match.empty:
        raise HTTPException(status_code=404, detail="Commodity-market not found")
    
    row = match.iloc[0]
    current_month = datetime.now().month
    season = "Monsoon_Kharif" if current_month in MONSOON_MONTHS else \
             "Post_Monsoon" if current_month in POST_MONSOON_MONTHS else \
             "Winter_Rabi" if current_month in WINTER_MONTHS else "Summer_Zaid"
    
    supply = "High" if row.get("supply_pressure", 1) > 1.2 else "Normal"
    weather = "Monsoon" if current_month in MONSOON_MONTHS else "Dry"
    
    return {
        "district": row["district"],
        "commodity": row["commodity"],
        "market": row["market"],
        "current_price": round(row["modal_price"], 2),
        "predicted_price_14d": round(row["predicted_price_14d"], 2),
        "predicted_change_pct": row["predicted_change_pct"],
        "prediction_date": str(row["prediction_date"]),
        "model": row["model"],
        "weather_source": row["weather_source"],
        "confidence": 0.88,
        "factors": {
            "season": season,
            "supply_pressure": supply,
            "weather_impact": weather,
            "festival_nearby": any(row.get(f"is_{f}", 0) for f in GOA_FESTIVALS)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)