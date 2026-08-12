"""
FarmIntel Backend API Server
Serves ML models for crop recommendation, fertilizer recommendation, and price prediction
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import joblib
import numpy as np
import pandas as pd
import json
import os
from pathlib import Path

app = FastAPI(title="FarmIntel API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model storage
models = {}
encoders = {}
lookups = {}

# Paths
BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models"
HYBRID_DIR = BASE_DIR / "hybrid_crop_model" / "models"
PRICE_DIR = BASE_DIR / "price_predictor" / "goa_model"

# Load models on startup
@app.on_event("startup")
async def load_models():
    global models, encoders, lookups
    
    try:
        # Load final_model (crop recommendation)
        models['rf_crop'] = joblib.load(MODELS_DIR / "rf_model.pkl")
        encoders['crop_label'] = joblib.load(MODELS_DIR / "label_encoder.pkl")
        
        with open(MODELS_DIR / "config.json") as f:
            lookups['config'] = json.load(f)
            
        with open(MODELS_DIR / "district_crop_map.json") as f:
            lookups['district_crop_map'] = json.load(f)
            
        with open(MODELS_DIR / "historical_lookup.json") as f:
            lookups['historical'] = json.load(f)
            
        print("✅ Loaded final_model (crop recommendation)")
    except Exception as e:
        print(f"⚠️ Failed to load final_model: {e}")
    
    try:
        # Load hybrid_crop_model
        models['rf_hybrid'] = joblib.load(HYBRID_DIR / "rf_model.pkl")
        models['xgb_hybrid'] = joblib.load(HYBRID_DIR / "xgb_model.pkl")
        encoders['hybrid_label'] = joblib.load(HYBRID_DIR / "label_encoder.pkl")
        print("✅ Loaded hybrid_crop_model")
    except Exception as e:
        print(f"⚠️ Failed to load hybrid_crop_model: {e}")
    
    try:
        # Load price prediction model
        models['xgb_price'] = joblib.load(PRICE_DIR / "goa_xgb_model.pkl")
        with open(PRICE_DIR / "goa_model_metadata.json") as f:
            lookups['price_metadata'] = json.load(f)
        print("✅ Loaded price prediction model")
    except Exception as e:
        print(f"⚠️ Failed to load price model: {e}")

# Request/Response Models
class CropRecommendRequest(BaseModel):
    N: float
    P: float
    K: float
    temperature: float
    humidity: float
    ph: float
    rainfall: float

class CropRecommendResponse(BaseModel):
    crop: str
    confidence: float
    alternatives: List[Dict[str, Any]]

class FertilizerRequest(BaseModel):
    crop: str
    soil: str
    N: Optional[float] = None
    P: Optional[float] = None
    K: Optional[float] = None
    PH: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    district: Optional[str] = None
    mode: Optional[str] = "auto"
    top_k: int = 5

class FertilizerResponse(BaseModel):
    recommended_fertilizers: List[str]
    top_matches: List[Dict[str, Any]]
    soil_nutrients: Dict[str, float]
    crop: str
    soil: str

class RotationRequest(BaseModel):
    prev_crop: str
    N: float
    P: float
    K: float
    top_n: int = 5

class RotationResponse(BaseModel):
    suggestions: List[Dict[str, Any]]

class RotationPlanRequest(BaseModel):
    season1_crop: str
    N: Optional[float] = None
    P: Optional[float] = None
    K: Optional[float] = None
    ph: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    district: Optional[str] = None
    mode: Optional[str] = "auto"
    top_n: int = 5

class PricePredictionRequest(BaseModel):
    district: str
    commodity: str
    market: str = "All"
    days: int = 14

class PricePredictionResponse(BaseModel):
    district: str
    commodity: str
    market: str
    current_price: float
    predicted_price_14d: float
    predicted_change_pct: float
    prediction_date: str
    model: str

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "models_loaded": list(models.keys()),
        "version": "1.0.0"
    }

# Crop Recommendation
@app.post("/predict", response_model=CropRecommendResponse)
async def predict_crop(request: CropRecommendRequest):
    if 'rf_crop' not in models:
        raise HTTPException(status_code=503, detail="Crop model not loaded")
    
    try:
        features = np.array([[
            request.N, request.P, request.K,
            request.temperature, request.humidity,
            request.ph, request.rainfall
        ]])
        
        # Get prediction probabilities
        probas = models['rf_crop'].predict_proba(features)[0]
        classes = encoders['crop_label'].classes_
        
        # Top prediction
        top_idx = np.argmax(probas)
        top_crop = classes[top_idx]
        confidence = float(probas[top_idx])
        
        # Top 3 alternatives
        top3_idx = np.argsort(probas)[-3:][::-1]
        alternatives = [
            {"crop": classes[i], "confidence": float(probas[i])}
            for i in top3_idx
        ]
        
        return CropRecommendResponse(
            crop=top_crop,
            confidence=confidence,
            alternatives=alternatives
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Fertilizer Recommendation
@app.post("/fertilizer/recommend", response_model=FertilizerResponse)
async def recommend_fertilizer(request: FertilizerRequest):
    # This would use the fertilizer dataset logic
    # For now, return mock data structure
    return FertilizerResponse(
        recommended_fertilizers=["Urea", "DAP", "MOP"],
        top_matches=[
            {"Fertilizer": "Urea", "Similarity": 0.95, "Remark": "High nitrogen"},
            {"Fertilizer": "DAP", "Similarity": 0.87, "Remark": "Balanced NPK"},
            {"Fertilizer": "MOP", "Similarity": 0.82, "Remark": "Potassium source"}
        ],
        soil_nutrients={"N": request.N or 0, "P": request.P or 0, "K": request.K or 0, "PH": request.PH or 7},
        crop=request.crop,
        soil=request.soil
    )

# Crop Rotation Suggestions
@app.post("/rotation/suggestions", response_model=RotationResponse)
async def rotation_suggestions(request: RotationRequest):
    # Mock response - implement actual logic
    return RotationResponse(
        suggestions=[
            {"crop": "Wheat", "score": 0.92},
            {"crop": "Chickpea", "score": 0.88},
            {"crop": "Mustard", "score": 0.85}
        ]
    )

# Crop Rotation Plan
@app.post("/rotation/plan", response_model=RotationResponse)
async def rotation_plan(request: RotationPlanRequest):
    # Mock response - implement actual logic
    return RotationResponse(
        suggestions=[
            {"season": "Kharif", "crop": request.season1_crop, "score": 0.95},
            {"season": "Rabi", "crop": "Wheat", "score": 0.90},
            {"season": "Summer", "crop": "Moong", "score": 0.85}
        ]
    )

# Default NPK from location
@app.post("/location/default-npk")
async def default_npk(request: Dict[str, Any]):
    # Mock response - implement actual location-based logic
    return {
        "N": 120.0,
        "P": 60.0,
        "K": 40.0,
        "ph": 6.5,
        "rainfall": 800,
        "temperature": 28.0
    }

# Price Prediction (14-day)
@app.post("/predict/14day", response_model=List[PricePredictionResponse])
async def predict_14day(request: PricePredictionRequest):
    if 'xgb_price' not in models:
        raise HTTPException(status_code=503, detail="Price model not loaded")
    
    # Mock response - implement actual prediction logic
    return [
        PricePredictionResponse(
            district=request.district,
            commodity=request.commodity,
            market=request.market,
            current_price=2500.0,
            predicted_price_14d=2650.0,
            predicted_change_pct=6.0,
            prediction_date=pd.Timestamp.now().strftime("%Y-%m-%d"),
            model="XGBoost"
        )
    ]

# Price Trajectory
@app.post("/predict/trajectory")
async def predict_trajectory(request: PricePredictionRequest):
    # Mock response
    trajectory = []
    base_price = 2500.0
    for day in range(request.days):
        change = np.random.normal(0, 0.02)
        base_price *= (1 + change)
        trajectory.append({
            "day": day + 1,
            "date": (pd.Timestamp.now() + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
            "predicted_price": round(base_price, 2),
            "change_from_prev_pct": round(change * 100, 2)
        })
    
    return [{
        "district": request.district,
        "commodity": request.commodity,
        "market": request.market,
        "current_price": 2500.0,
        "trajectory": trajectory
    }]

# Single Prediction with confidence
@app.get("/predict/single")
async def single_prediction(district: str, commodity: str, market: str):
    return {
        "district": district,
        "commodity": commodity,
        "market": market,
        "current_price": 2500.0,
        "predicted_price_14d": 2650.0,
        "predicted_change_pct": 6.0,
        "prediction_date": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "model": "XGBoost",
        "confidence": 0.85,
        "factors": {
            "season": "Kharif",
            "supply_pressure": "Moderate",
            "weather_impact": "Favorable",
            "festival_nearby": False
        }
    }

# Commodities list
@app.get("/commodities")
async def get_commodities():
    return {"commodities": ["Rice", "Wheat", "Maize", "Tomato", "Onion", "Potato", "Cotton", "Sugarcane"]}

# Markets list
@app.get("/markets")
async def get_markets(district: Optional[str] = None):
    markets = [
        {"district": "North Goa", "market": "Mapusa"},
        {"district": "North Goa", "market": "Panaji"},
        {"district": "South Goa", "market": "Margao"},
        {"district": "Belagavi", "market": "Belagavi APMC"},
        {"district": "Bengaluru", "market": "Yeshwanthpur"}
    ]
    if district:
        markets = [m for m in markets if m["district"].lower() == district.lower()]
    return {"markets": markets}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
