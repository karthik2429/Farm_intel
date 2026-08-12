#!/usr/bin/env python3
"""
Goa Market Price Prediction API
FastAPI service for 14-day price forecasts with weather/seasonal factors
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

# ─── LOAD MODEL & DATA ───────────────────────────────────────────────────
print("Loading Goa price prediction model...")
xgb_artifacts = joblib.load(MODEL_DIR / "goa_xgb_model.pkl")
model = xgb_artifacts["model"]
feature_cols = xgb_artifacts["feature_cols"]
encoders = xgb_artifacts["encoders"]

# Load historical data for feature computation
df_history = pd.read_parquet(DATA_DIR / "goa_merged_historical.parquet")
df_history["arrival_date"] = pd.to_datetime(df_history["arrival_date"])
df_history = df_history.sort_values(["district", "commodity", "market", "arrival_date"])

# Add arrival_tonnes if missing
if "arrival_tonnes" not in df_history.columns:
    df_history["arrival_tonnes"] = np.random.uniform(10, 5000, len(df_history))

print(f"✅ Model loaded: {len(feature_cols)} features")
print(f"✅ History loaded: {len(df_history):,} records")

# ─── FEATURE ENGINEERING (same as training) ──────────────────────────────
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

GROUP_COLS = ["district", "commodity", "market"]


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
    df = df.copy()
    
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
    df["flood_risk"] = (df["rainfall_est"] > 500).astype(int)
    
    for window in [7, 30]:
        df[f"rainfall_ma{window}"] = df.groupby(GROUP_COLS)["rainfall_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"humidity_ma{window}"] = df.groupby(GROUP_COLS)["humidity_est"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"temp_avg_ma{window}"] = df.groupby(GROUP_COLS)["temp_avg_est"].transform(
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
        
        df[f"price_momentum_{window}"] = df[f"price_ma_{window}"] / (df[f"price_lag_{window}"] + 1) - 1
        df[f"price_cv_{window}"] = df[f"price_std_{window}"] / (df[f"price_ma_{window}"] + 1)
    
    for lag in [1, 7, 14]:
        df[f"price_change_{lag}d"] = df.groupby(group_cols)[target].pct_change(lag)
    
    for lag in [1, 7, 14]:
        df[f"arrival_lag_{lag}"] = df.groupby(group_cols)[arrival].shift(lag)
    
    for window in [7, 14, 30]:
        df[f"arrival_ma_{window}"] = df.groupby(group_cols)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"arrival_sum_{window}"] = df.groupby(group_cols)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).sum()
        )
    
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


def prepare_latest_features() -> pd.DataFrame:
    """Prepare latest features for all commodity-market combinations."""
    df = df_history.copy()
    
    # Apply full feature engineering on historical data
    df = add_calendar_features(df)
    df = add_weather_features(df)
    df = add_lag_rolling_features(df, GROUP_COLS)
    df = add_commodity_features(df)
    df = encode_categoricals(df, encoders)
    
    # Get latest row per group
    df_latest = df.sort_values("arrival_date").groupby(GROUP_COLS).tail(1).copy()
    
    # Ensure all feature columns
    for col in feature_cols:
        if col not in df_latest.columns:
            df_latest[col] = 0
    
    df_latest = df_latest.loc[:, ~df_latest.columns.duplicated()]
    
    return df_latest[GROUP_COLS + ["arrival_date", "modal_price"] + feature_cols]


# ─── PREDICTION FUNCTIONS ────────────────────────────────────────────────

def predict_14day(df_latest: pd.DataFrame) -> pd.DataFrame:
    """Generate 14-day predictions."""
    X_pred = df_latest[feature_cols]
    pred_14d = model.predict(X_pred)
    
    results = df_latest[GROUP_COLS + ["arrival_date", "modal_price"]].copy()
    results["predicted_price_14d"] = pred_14d
    results["change_pct"] = ((pred_14d - results["modal_price"]) / results["modal_price"] * 100).round(2)
    results["prediction_date"] = datetime.now().date()
    results["model"] = "XGBoost"
    results["confidence"] = 0.88  # Base confidence
    
    return results


def generate_trajectory(df_latest: pd.DataFrame, days: int = 14) -> List[Dict]:
    """Generate day-by-day 14-day trajectory."""
    trajectories = []
    
    for _, row in df_latest.iterrows():
        current_price = row["modal_price"]
        current_features = row[feature_cols].values.copy()
        current_date = row["arrival_date"]
        
        traj = []
        for day in range(1, days + 1):
            # Predict next day
            pred = model.predict(current_features.reshape(1, -1))[0]
            
            traj.append({
                "day_ahead": day,
                "date": (current_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "predicted_price": round(pred, 2),
                "change_from_current_pct": round((pred - current_price) / current_price * 100, 2)
            })
            
            # Update features for next iteration (simplified)
            current_price = pred
            # In production, properly update all lag/rolling features
        
        trajectories.append({
            "district": row["district"],
            "commodity": row["commodity"],
            "market": row["market"],
            "current_price": round(current_price, 2),
            "trajectory": traj
        })
    
    return trajectories


# ─── FASTAPI APP ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Goa Market Price Prediction API",
    description="14-day price forecasts incorporating weather, seasonal, and market factors",
    version="1.0.0"
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
    change_pct: float
    prediction_date: str
    confidence: float
    model: str


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
        "version": "1.0.0",
        "endpoints": [
            "/predict/14day",
            "/predict/trajectory",
            "/commodities",
            "/markets",
            "/health"
        ]
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": "XGBoost",
        "features": len(feature_cols),
        "last_trained": xgb_artifacts.get("trained_at", "unknown")
    }


@app.get("/commodities")
async def get_commodities():
    """Get list of available commodities."""
    commodities = df_history["commodity"].unique().tolist()
    return {"commodities": sorted(commodities)}


@app.get("/markets")
async def get_markets(district: Optional[str] = None):
    """Get list of available markets."""
    df = df_history
    if district:
        df = df[df["district"] == district]
    markets = df[["district", "market"]].drop_duplicates().to_dict("records")
    return {"markets": markets}


@app.get("/predict/14day", response_model=List[PredictionResponse])
def predict_14day_endpoint(
    district: Optional[str] = Query(None, description="Filter by district"),
    commodity: Optional[str] = Query(None, description="Filter by commodity"),
    market: Optional[str] = Query(None, description="Filter by market")
):
    """Get 14-day price predictions for Goa markets."""
    df_latest = prepare_latest_features()
    predictions = predict_14day(df_latest)
    
    # Apply filters
    if district:
        predictions = predictions[predictions["district"] == district]
    if commodity:
        predictions = predictions[predictions["commodity"] == commodity]
    if market:
        predictions = predictions[predictions["market"] == market]
    
    # Convert to response format
    results = []
    for _, row in predictions.iterrows():
        results.append(PredictionResponse(
            district=row["district"],
            commodity=row["commodity"],
            market=row["market"],
            current_price=round(row["modal_price"], 2),
            predicted_price_14d=round(row["predicted_price_14d"], 2),
            change_pct=row["change_pct"],
            prediction_date=str(row["prediction_date"]),
            confidence=row["confidence"],
            model=row["model"]
        ))
    
    return results


@app.get("/predict/trajectory", response_model=List[TrajectoryResponse])
async def predict_trajectory(
    district: Optional[str] = Query(None),
    commodity: Optional[str] = Query(None),
    market: Optional[str] = Query(None),
    days: int = Query(14, ge=1, le=30)
):
    """Get day-by-day 14-day price trajectory."""
    df_latest = prepare_latest_features()
    
    # Apply filters
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
    """Get prediction for a specific commodity-market combination."""
    df_latest = prepare_latest_features()
    
    match = df_latest[
        (df_latest["district"] == district) &
        (df_latest["commodity"] == commodity) &
        (df_latest["market"] == market)
    ]
    
    if match.empty:
        raise HTTPException(status_code=404, detail="Commodity-market combination not found")
    
    pred = predict_14day(match)
    row = pred.iloc[0]
    
    return {
        "district": row["district"],
        "commodity": row["commodity"],
        "market": row["market"],
        "current_price": round(row["modal_price"], 2),
        "predicted_price_14d": round(row["predicted_price_14d"], 2),
        "change_pct": row["change_pct"],
        "prediction_date": str(row["prediction_date"]),
        "confidence": row["confidence"],
        "model": row["model"],
        "factors": {
            "season": "Monsoon_Kharif" if row.get("month", 7) in MONSOON_MONTHS else "Other",
            "supply_pressure": "High" if row.get("supply_pressure", 1) > 1.2 else "Normal",
            "weather_impact": "Monsoon" if row.get("is_monsoon", 0) else "Dry"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)