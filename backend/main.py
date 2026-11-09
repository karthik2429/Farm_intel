"""
FarmIntel Backend API Server

Serves ML models for crop recommendation, fertilizer recommendation,
crop rotation planning, and price prediction (Goa XGBoost + real weather).

Response shapes match the frontend contracts in src/lib/api.ts, priceApi.ts
and the page components (CropRotationPage, FertilizerRecommendationPage,
PricePredictionPage, HomeDashboard).
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
import json
from datetime import datetime
from pathlib import Path

import hashlib

import joblib
import numpy as np
import pandas as pd
import requests

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "price_predictor" / "goa_model"))

from utils.utils import (  # noqa: E402
    get_rotation_suggestions,
    plan_two_season_rotation,
    recommend_fertilizer as dataset_recommend_fertilizer,
    get_default_npk_from_location,
    get_lat_lon_from_district,
    get_weather,
)
import price_engine  # noqa: E402
import district_data  # noqa: E402
import mandi_prices  # noqa: E402
import price_forecast  # noqa: E402
import crop_info  # noqa: E402
import price_store  # noqa: E402
import chat as chat_service  # noqa: E402
import price_factors  # noqa: E402
from config import settings, service_status  # noqa: E402

app = FastAPI(title="FarmIntel API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model storage
models: Dict[str, Any] = {}
encoders: Dict[str, Any] = {}
lookups: Dict[str, Any] = {}

MODELS_DIR = BASE_DIR / "models"


@app.on_event("startup")
async def load_models():
    global models, encoders, lookups
    try:
        models["rf_crop"] = joblib.load(MODELS_DIR / "rf_model.pkl")
        encoders["crop_label"] = joblib.load(MODELS_DIR / "label_encoder.pkl")
        with open(MODELS_DIR / "config.json") as f:
            lookups["config"] = json.load(f)
        with open(MODELS_DIR / "district_crop_map.json") as f:
            lookups["district_crop_map"] = json.load(f)
        with open(MODELS_DIR / "historical_lookup.json") as f:
            lookups["historical"] = json.load(f)
        print(f"✅ crop model loaded ({len(encoders['crop_label'].classes_)} crops)")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Failed to load crop model: {e}")


# ─────────────────────── Request / Response models ───────────────────────

class CropRecommendRequest(BaseModel):
    N: Optional[float] = None
    P: Optional[float] = None
    K: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    ph: Optional[float] = 6.5
    rainfall: Optional[float] = None
    district: Optional[str] = None
    state: Optional[str] = None
    season: Optional[str] = "kharif"
    lat: Optional[float] = None
    lon: Optional[float] = None
    mode: Optional[str] = "auto"


class RotationRequest(BaseModel):
    prev_crop: str
    N: float
    P: float
    K: float
    top_n: int = 5


class RotationPlanRequest(BaseModel):
    season1_crop: str
    N: Optional[float] = None
    P: Optional[float] = None
    K: Optional[float] = None
    ph: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    district: Optional[str] = None
    state: Optional[str] = None
    mode: Optional[str] = "auto"
    top_n: int = 3


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
    state: Optional[str] = None
    mode: Optional[str] = "auto"
    top_k: int = 5


class PricePredictionRequest(BaseModel):
    # No hardcoded default district: the caller sends the farmer's saved
    # district, and the backend falls back district -> state -> India itself.
    district: Optional[str] = None
    state: Optional[str] = None
    commodity: Optional[str] = None
    market: Optional[str] = "All"
    days: int = 14


# ─────────────────────── Helpers ─────────────────────────────────────────

_DISTRICT_COORDS = {
    "belagavi": (15.85, 74.5), "bengaluru urban": (12.97, 77.59),
    "bengaluru rural": (13.2, 77.6), "mysuru": (12.3, 76.6),
    "koppal": (15.35, 76.15), "tumakuru": (13.34, 77.1),
    "nashik": (20.0, 73.8), "pune": (18.52, 73.86),
    "ludhiana": (30.9, 75.85), "bhopal": (23.26, 77.4),
    "north goa": (15.5, 73.83), "south goa": (15.2, 74.0),
}


_GEOCODE_CACHE: dict = {}


def _geocode_open_meteo(district: str, state: Optional[str] = None):
    """
    District -> (lat, lon) via Open-Meteo's geocoder.

    The weather provider is already Open-Meteo, so this keeps coordinates and
    forecast on one source and needs no API key. Cached; never raises.
    """
    key = f"{(district or '').strip().lower()}|{(state or '').strip().lower()}"
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]
    coords = None
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": district, "count": 10, "language": "en",
                    "format": "json", "countryCode": "IN"},
            timeout=6,
        )
        results = (resp.json() or {}).get("results") or []
        state_key = (state or "").strip().lower()
        picked = None
        for hit in results:
            if hit.get("latitude") is None or hit.get("longitude") is None:
                continue
            admin = f"{hit.get('admin1') or ''} {hit.get('admin2') or ''}".lower()
            if not state_key or state_key in admin:
                picked = hit
                break
        if picked:
            coords = (float(picked["latitude"]), float(picked["longitude"]))
    except Exception:  # noqa: BLE001
        coords = None
    _GEOCODE_CACHE[key] = coords
    return coords


def _resolve_coords(district: Optional[str], lat: Optional[float],
                    lon: Optional[float], mode: str = "auto",
                    state: Optional[str] = None):
    """Resolve (lat, lon) from coords, known districts, or geocoding."""
    if mode == "coords" and lat is not None and lon is not None:
        return lat, lon
    if lat is not None and lon is not None:
        return lat, lon
    if district:
        key = district.strip().lower()
        if key in _DISTRICT_COORDS:
            return _DISTRICT_COORDS[key]
        geo = district_data.geocode_district(district, state)
        if geo:
            return geo
        geo = _geocode_open_meteo(district, state)
        if geo:
            return geo
        la, lo = get_lat_lon_from_district(district)
        if la is not None and lo is not None:
            return la, lo
    return lat, lon


def _weather_lookup(lat: Optional[float], lon: Optional[float]):
    """Live Open-Meteo weather with a monsoon-aware India fallback.

    Returns (temperature, humidity, rainfall, source). The source is reported
    for every answer: a provider outage must never be presented as a live
    reading, because the UI labels the card from this value.
    """
    try:
        if lat is not None and lon is not None:
            temp, humidity, rainfall = get_weather(lat, lon)
            return (float(temp), float(humidity), float(rainfall), "open_meteo")
    except Exception:  # noqa: BLE001
        pass
    m = pd.Timestamp.now().month
    if m in (6, 7, 8, 9):
        return 27.0, 85.0, 12.0, "national_fallback"
    if m in (10, 11):
        return 28.0, 75.0, 3.0, "national_fallback"
    if m in (12, 1, 2):
        return 24.0, 60.0, 0.5, "national_fallback"
    return 31.0, 55.0, 1.0, "national_fallback"


def _weather_or_default(lat: Optional[float], lon: Optional[float]):
    temp, humidity, rainfall, _source = _weather_lookup(lat, lon)
    return temp, humidity, rainfall


def _fill_npk_from_location(payload: FertilizerRequest):
    """Resolve missing N/P/K/PH from the district's real soil survey."""
    if None not in (payload.N, payload.P, payload.K, payload.PH):
        return payload.N, payload.P, payload.K, payload.PH
    defaults = district_data.default_soil_for(
        payload.district, getattr(payload, "state", None),
        payload.lat, payload.lon)
    if not defaults:
        lat, lon = _resolve_coords(payload.district, payload.lat,
                                   payload.lon, payload.mode or "auto",
                                   state=getattr(payload, "state", None))
        defaults = get_default_npk_from_location(
            lat=lat, lon=lon,
            district=(payload.district or "").lower() or None,
            mode="coords" if (lat is not None and lon is not None) else "auto")
    n = payload.N if payload.N is not None else defaults.get("N", 90)
    p = payload.P if payload.P is not None else defaults.get("P", 40)
    k = payload.K if payload.K is not None else defaults.get("K", 40)
    ph = payload.PH if payload.PH is not None else defaults.get("ph", 6.5)
    return n, p, k, ph


# ─────────────────────── Health ──────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "models_loaded": list(models.keys()),
        "price_model": price_engine.model_loaded(),
        "price_error": price_engine.load_error(),
        "version": "3.0.0",
        "port": settings.backend_port,
    }


@app.get("/config/status")
async def config_status():
    """
    Which optional services are configured. Booleans only — a key value is
    never returned. The dev-only "Setup status" panel reads this to show
    exactly what is missing and where to get it.
    """
    return service_status()


# ─────────────────────── Crop recommendation ─────────────────────────────

@app.post("/predict")
async def predict_crop(request: CropRecommendRequest):
    """
    District-aware crop recommendation.

    Blends the RandomForest ML model with the district's real soil survey
    (DES 2024-25), its historical cropping pattern, season, live climate and
    the crop's real mandi price x published yield (gross return per hectare).
    Falls back to pure ML when the district is unknown.

    Returns {crop, confidence, alternatives, Top Crops, district, season,
    soil_used} for CropRecommendationsPage and HomeDashboard.
    """
    try:
        # ---- resolve location (name or coordinates) ----
        lat, lon = _resolve_coords(request.district, request.lat, request.lon,
                                   request.mode or "auto",
                                   state=request.state)

        # ---- fill missing soil/weather values from district + live data ----
        prof = district_data.resolve_district(
            request.district, request.state,
            lat if request.mode == "coords" else None,
            lon if request.mode == "coords" else None)
        soil = (prof or {}).get("soil") if prof else None
        soil_valid = bool(soil) and any(
            (soil.get(k) or 0) > 0 for k in ("N", "P", "K"))

        N = request.N if request.N is not None else (
            soil.get("N") if soil_valid else 90)
        P = request.P if request.P is not None else (
            soil.get("P") if soil_valid else 40)
        K = request.K if request.K is not None else (
            soil.get("K") if soil_valid else 40)
        ph = request.ph if request.ph is not None else (
            soil.get("ph") if soil_valid else 6.5)

        temp = request.temperature
        hum = request.humidity
        rain = request.rainfall
        if (temp is None or hum is None or rain is None) and lat and lon:
            try:
                wt, wh, wr = get_weather(lat, lon)
                temp = temp if temp is not None else wt
                hum = hum if hum is not None else wh
                rain = rain if rain is not None else wr
            except Exception:  # noqa: BLE001
                pass
        temp = float(temp if temp is not None else 27.0)
        hum = float(hum if hum is not None else 70.0)
        rain = float(rain if rain is not None else 5.0)

        result = district_data.recommend_for_district(
            N=N, P=P, K=K, ph=float(ph),
            temperature=temp, humidity=hum, rainfall=rain,
            district=request.district, state=request.state,
            lat=lat if request.mode == "coords" else None,
            lon=lon if request.mode == "coords" else None,
            season=request.season or "kharif",
            top_n=5,
        )
        # Report the soil values actually scored, not the district survey
        # defaults: a caller that sent N=120 must not be told N=46.
        result["soil_used"] = {
            "N": round(float(N), 1), "P": round(float(P), 1),
            "K": round(float(K), 1), "ph": round(float(ph), 1)}
        result["weather"] = {"temperature": round(temp, 1),
                             "humidity": round(hum, 1),
                             "rainfall": round(rain, 1)}
        # The district survey behind the soil score, so the result can show
        # which soil it actually matched against instead of a bare percentage.
        result["soil_survey"] = (
            {"source": "DES district soil test data 2024-25",
             "district": (prof or {}).get("district"),
             "state": (prof or {}).get("state"),
             "N": round(float(soil["N"]), 1), "P": round(float(soil["P"]), 1),
             "K": round(float(soil["K"]), 1), "ph": round(float(soil["ph"]), 1)}
            if soil_valid else None)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))

    results = result.get("results") or []
    if not results:
        raise HTTPException(status_code=503, detail="No recommendation available")

    ranked = [(r["crop"], float(r["display_score"])) for r in results]
    # Each alternative carries the evidence behind its rank: soil fit, climate
    # fit, how much of the district's area it already holds, and what it earns
    # per hectare at the real mandi price. The crop page renders them instead
    # of asking the farmer to trust one number.
    factor_keys = (
        "ml_prob", "soil_fit", "climate_fit", "season_fit", "hist_score",
        "region_share", "locality", "market_score", "market_price",
        "price_commodity", "market_price_source", "market_price_date",
        "market_price_scope", "market_price_badge", "price_market",
        "price_district", "yield_t_ha", "gross_return_per_ha",
    )
    alternatives = [
        {"crop": r["crop"], "confidence": round(float(r["display_score"]), 4),
         **{k: r[k] for k in factor_keys if k in r}}
        for r in results[:4]
    ]
    return {
        "crop": ranked[0][0],
        "confidence": round(ranked[0][1], 4),
        "alternatives": alternatives,
        "Top Crops": [[c, round(s, 4)] for c, s in ranked[:3]],
        "district": result.get("resolved_district"),
        "state": result.get("resolved_state"),
        "season": result.get("season"),
        "soil_used": result.get("soil_used"),
        "soil_survey": result.get("soil_survey"),
        "weather": result.get("weather"),
        "economics": result.get("economics"),
        "note": result.get("note"),
    }


# ─────────────────────── Crop rotation ───────────────────────────────────

@app.post("/rotation/suggestions")
async def rotation_suggestions(request: RotationRequest):
    """NPK-depletion based next-crop scoring (utils engine + master xlsx)."""
    try:
        result = get_rotation_suggestions(
            request.prev_crop, request.N, request.P, request.K, request.top_n)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
    return result  # may contain "error" key; frontend toasts it


@app.post("/rotation/plan")
async def rotation_plan(request: RotationPlanRequest):
    """
    Full 2-season plan: {season1, season2_options, soil_after_s1,
    season3_preview, warnings} — exactly what CropRotationPage renders.
    """
    lat, lon = _resolve_coords(request.district, request.lat, request.lon,
                               request.mode or "auto", state=request.state)
    try:
        plan = plan_two_season_rotation(
            season1_crop=request.season1_crop,
            N=request.N, P=request.P, K=request.K, ph=request.ph,
            lat=lat, lon=lon,
            district=(request.district or "").strip().lower() or None,
            mode="coords" if (lat is not None and lon is not None) else "auto",
            top_n=request.top_n or 3,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in plan:
        return plan  # frontend checks data.error and toasts
    return plan


# ─────────────────────── Fertilizer ──────────────────────────────────────

# Frontend crop names -> fertilizer dataset crop names
_FERT_ALIAS = {
    "rice": "rice", "wheat": "wheat", "maize": "maize", "cotton": "cotton",
    "sugarcane": "sugarcane", "chickpea": "chickpea",
    "pigeon pea": "pigeon peas", "green gram": "mung bean",
    "black gram": "black gram", "lentil": "lentil",
    "groundnut": "ground nut", "kidney bean": "kidney beans",
    "moth bean": "moth beans", "coconut": "coconut", "banana": "banana",
    "mango": "mango", "grapes": "grapes", "orange": "orange",
    "papaya": "papaya", "pomegranate": "pomegranate",
    "muskmelon": "muskmelon", "watermelon": "watermelon",
    "millet": "millet", "jute": "jute", "tea": "tea", "coffee": "coffee",
    "tobacco": "tobacco", "rubber": "rubber", "peas": "peas",
    "apple": "apple", "adzuki beans": "adzuki beans",
}


def _normalize_soil(soil: str) -> str:
    """Map UI soil names onto the 5 soils the dataset actually has
    (acidic soil, alkaline soil, loamy soil, neutral soil, peaty soil) so
    cosine matching runs instead of instantly falling back."""
    s = (soil or "").strip().lower()
    if not s:
        return "loamy soil"
    if "loam" in s:
        return "loamy soil"
    if "peat" in s:
        return "peaty soil"
    if "acid" in s:
        return "acidic soil"
    if "alkaline" in s:
        return "alkaline soil"
    # Black / Red / Clayey / Sandy -> classify by district soil pH profile
    return ""  # caller resolves via district soil

# Ideal NPK targets for crops not in the dataset (rule-based fallback)
_FERT_TARGETS = {
    "soybean": (30, 60, 40), "mustard": (80, 45, 40),
    "sunflower": (60, 55, 45), "sesame": (50, 40, 40),
    "potato": (110, 60, 70), "tomato": (90, 55, 55),
    "onion": (90, 45, 50), "chilli": (100, 50, 50),
    "turmeric": (60, 50, 50), "ginger": (75, 50, 50),
    "jowar": (80, 40, 40), "bajra": (80, 40, 40), "ragi": (50, 40, 40),
    "barley": (60, 30, 30), "castor": (50, 30, 30),
    "linseed": (60, 30, 30), "safflower": (50, 25, 25),
    "niger": (40, 30, 20), "horse gram": (20, 30, 20),
    "cowpea": (20, 40, 25), "field pea": (25, 50, 30),
    "lablab bean": (20, 40, 25), "okra": (90, 45, 50),
    "brinjal": (90, 50, 50), "cabbage": (100, 55, 55),
    "cauliflower": (100, 55, 55), "cucumber": (70, 40, 45),
    "pumpkin": (60, 40, 45), "bottle gourd": (70, 40, 45),
    "bitter gourd": (70, 40, 45), "watermelon": (60, 40, 45),
    "muskmelon": (60, 40, 45), "guava": (70, 50, 50),
    "garlic": (90, 45, 50), "coriander": (30, 25, 25),
    "cumin": (30, 20, 20), "fennel": (40, 25, 25),
    "fenugreek": (30, 30, 25), "foxtail millet": (50, 30, 30),
    "kodo millet": (50, 30, 30), "little millet": (45, 30, 30),
    "barnyard millet": (45, 30, 30), "proso millet": (50, 30, 30),
    "green gram": (20, 40, 25), "black gram": (20, 40, 25),
    "ground nut": (25, 40, 40), "pigeon peas": (25, 50, 30),
    "kidney beans": (80, 45, 40), "moth beans": (20, 35, 25),
    "adzuki beans": (30, 45, 35), "mung bean": (20, 40, 25),
}


def _rule_based_fertilizer(crop: str, n: float, p: float, k: float,
                           ph: float) -> Dict[str, Any]:
    """Transparent NPK-gap analysis for crops missing from the dataset."""
    tgt = _FERT_TARGETS.get(crop.lower(), (90, 45, 45))
    gaps = {"N": max(0.0, tgt[0] - n), "P": max(0.0, tgt[1] - p),
            "K": max(0.0, tgt[2] - k)}
    recs, matches = [], []
    if gaps["N"] > 20:
        recs.append("Urea")
        matches.append({"Fertilizer": "Urea",
                        "Similarity": round(min(1, gaps["N"] / 120), 2),
                        "Remark": f"Apply ~{round(gaps['N'] * 2)} kg/ha to close N gap"})
    if gaps["P"] > 15:
        recs.append("DAP")
        matches.append({"Fertilizer": "DAP",
                        "Similarity": round(min(1, gaps["P"] / 60), 2),
                        "Remark": f"Apply ~{round(gaps['P'] * 2.2)} kg/ha for phosphorus"})
    if gaps["K"] > 15:
        recs.append("Muriate of Potash (MOP)")
        matches.append({"Fertilizer": "Muriate of Potash (MOP)",
                        "Similarity": round(min(1, gaps["K"] / 70), 2),
                        "Remark": f"Apply ~{round(gaps['K'] * 1.7)} kg/ha to close K gap"})
    if not recs:
        recs = ["Balanced NPK (19:19:19) foliar spray"]
        matches.append({"Fertilizer": "NPK 19:19:19", "Similarity": 0.6,
                        "Remark": "Soil nutrients already near crop targets"})
    if ph < 5.5:
        recs.append("Agricultural Lime")
        matches.append({"Fertilizer": "Lime", "Similarity": 0.55,
                        "Remark": f"Soil acidic (pH {ph}) - apply lime before sowing"})
    elif ph > 8.5:
        recs.append("Gypsum")
        matches.append({"Fertilizer": "Gypsum", "Similarity": 0.55,
                        "Remark": f"Soil alkaline (pH {ph}) - gypsum helps"})
    return {
        "recommended_fertilizers": recs,
        "top_matches": matches,
        "soil_nutrients": {"N": round(float(n), 1), "P": round(float(p), 1),
                           "K": round(float(k), 1), "PH": round(float(ph), 1)},
        "crop": crop,
        "source": "rule_based",
    }


@app.post("/fertilizer/recommend")
async def recommend_fertilizer(request: FertilizerRequest):
    """
    Dataset cosine-similarity matching (fertilizer.ipynb logic) with a
    transparent rule-based fallback for crops not in the dataset.
    Response shape matches FertilizerRecommendationPage.
    """
    try:
        n, p, k, ph = _fill_npk_from_location(request)
    except Exception:  # noqa: BLE001
        n, p, k, ph = request.N or 90, request.P or 40, request.K or 40, request.PH or 6.5

    key = request.crop.strip().lower()
    dataset_crop = _FERT_ALIAS.get(key, key)
    soil_key = _normalize_soil(request.soil)
    if not soil_key:
        # Black/Red/Clayey/Sandy: classify by the district's real pH profile
        prof = district_data.default_soil_for(
            request.district, getattr(request, "state", None),
            request.lat, request.lon)
        ph_hint = float((prof or {}).get("ph") or ph or 6.5)
        if ph_hint < 6.0:
            soil_key = "acidic soil"
        elif ph_hint > 7.5:
            soil_key = "alkaline soil"
        else:
            soil_key = "neutral soil"
    try:
        result = dataset_recommend_fertilizer(
            dataset_crop, soil_key, n, p, k, ph, top_k=request.top_k)
    except Exception as e:  # noqa: BLE001
        print(f"[fertilizer] dataset engine failed: {e}")
        result = None

    if result is None or len(result) == 0:
        return _rule_based_fertilizer(request.crop, n, p, k, ph)

    fertilizers = result["Fertilizer"].value_counts().head(3).index.tolist()
    top_matches = result[["Fertilizer", "Similarity", "Remark"]].head(5).to_dict("records")
    return {
        "recommended_fertilizers": fertilizers,
        "top_matches": top_matches,
        "soil_nutrients": {"N": round(float(n), 1), "P": round(float(p), 1),
                           "K": round(float(k), 1), "PH": round(float(ph), 1)},
        "crop": request.crop,
        "soil": request.soil,
        "source": "dataset",
    }


# ─────────────────────── Location defaults ───────────────────────────────

@app.post("/location/default-npk")
async def default_npk(request: Dict[str, Any]):
    """
    Real per-district soil defaults (DES district soil test survey) with
    live weather; falls back to sensible India-wide values only when the
    district is unknown.
    """
    lat = request.get("lat")
    lon = request.get("lon")
    district = request.get("district")
    state = request.get("state")
    mode = request.get("mode", "auto")

    prof = district_data.resolve_district(district, state, lat, lon)
    rlat, rlon = _resolve_coords(district, lat, lon, mode or "auto",
                                 state=state)
    if prof and not rlat:
        rlat, rlon = prof.get("lat"), prof.get("lon")

    try:
        temp, humidity, rainfall = _weather_or_default(rlat, rlon)
    except Exception:  # noqa: BLE001
        temp, humidity, rainfall = 27.0, 80.0, 5.0

    soil = (prof or {}).get("soil")
    soil_valid = bool(soil) and any(
        (soil.get(k) or 0) > 0 for k in ("N", "P", "K"))
    if soil_valid:
        return {
            "N": round(float(soil["N"]), 1),
            "P": round(float(soil["P"]), 1),
            "K": round(float(soil["K"]), 1),
            "ph": round(float(soil["ph"]), 1),
            "rainfall": round(float(rainfall), 1),
            "temperature": round(float(temp), 1),
            "humidity": round(float(humidity), 1),
            "district": prof.get("district"),
            "state": prof.get("state"),
            "source": "district_soil_survey",
        }

    # Fallbacks: geocoded weather + neutral NPK when district unknown
    return {
        "N": 90, "P": 40, "K": 40, "ph": 6.5,
        "rainfall": round(float(rainfall), 1),
        "temperature": round(float(temp), 1),
        "humidity": round(float(humidity), 1),
        "district": (prof or {}).get("district"),
        "state": (prof or {}).get("state"),
        "source": "fallback",
    }


# ─────────────────────────── Mandi prices ──────────────────────────────────

# ─────────────────────────── AI assistant ────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    district: Optional[str] = None
    state: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    lang: Optional[str] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    crops: Optional[List[str]] = None
    season: Optional[str] = None
    land_size: Optional[float] = None
    land_unit: Optional[str] = None
    soil: Optional[Dict[str, Any]] = None


LANG_NAMES = {
    "en": "English", "hi": "Hindi", "kn": "Kannada", "te": "Telugu",
    "ta": "Tamil", "ml": "Malayalam", "mr": "Marathi", "gu": "Gujarati",
    "bn": "Bengali", "pa": "Punjabi", "or": "Odia",
}


@app.post("/chat")
async def ai_chat(request: ChatRequest, http: Request):
    """
    Kisan assistant.

    Price, forecast, navigation and scheme questions are answered straight
    from the mandi database — no LLM, no cost, no invention. Only free-form
    advice reaches a free LLM (Gemini -> Groq -> OpenRouter -> Ollama).
    Rate limited per user per hour and globally. When no LLM key is set the
    reply explains exactly what is missing and what still works.
    """
    turns = [
        {"role": (m.role if m.role in ("user", "assistant") else "user"),
         "content": str(m.content)[:4000]}
        for m in request.messages if m.content and m.content.strip()
    ]
    if not turns:
        raise HTTPException(status_code=422, detail="Empty conversation")

    user_key = request.user_id or (
        hashlib.sha256((http.client.host if http.client else "?").encode()).hexdigest()[:16]
    )
    err = chat_service.check_rate(user_key)
    if err:
        raise HTTPException(status_code=429, detail=err)

    lang = (request.lang or "en").lower()
    if lang not in LANG_NAMES:
        lang = "en"

    ctx = {
        "lang": lang,
        "lang_name": LANG_NAMES[lang],
        "district": request.district,
        "state": request.state,
        "name": (request.name or "").split(" ")[0],
        "crops": request.crops or [],
        "season": request.season,
        "land_size": request.land_size,
        "land_unit": request.land_unit,
        "soil": request.soil,
    }

    question = turns[-1]["content"]
    try:
        result = chat_service.answer(question, ctx, turns[:-1])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"Assistant request failed: {exc}")

    return {
        **result,
        "providers_available": chat_service.providers(),
        "rate_limit_per_hour": settings.chat_rate_limit_per_user_per_hour,
    }


@app.get("/market/price")
async def market_price(commodity: str, district: Optional[str] = None,
                       state: Optional[str] = None, strict: bool = False):
    """
    Best-effort mandi price: Goa local history, bundled district snapshot,
    live AGMARKNET (self-healing probe), then MSP reference.

    Always answers 200 - when nothing is available the body carries
    `price: null` + `source: "unavailable"` so the frontend can render
    "--" without console 404 noise.
    """
    # get_price refreshes the district's whole live feed first when strict, so
    # a district page shows today's trade for every crop it reports instead of
    # a mix of today's live rows and a week-old cache.
    result = mandi_prices.get_price(commodity, district, state,
                                    strict_district=strict)
    if not result:
        where = ", ".join(p for p in (district, state) if p)
        return {
            "commodity": commodity,
            "district": district,
            "state": state,
            "market": "",
            "price": None,
            "min_price": None,
            "max_price": None,
            "unit": "₹/quintal",
            "source": "unavailable",
            # Same keys as a successful payload: the UI reads is_real/badge
            # unconditionally when drawing the honesty chip.
            "is_real": False,
            "badge": "unavailable",
            "scope": "district" if district else ("state" if state else "india"),
            "detail": (f"No AGMARKNET rate for {commodity}"
                       + (f" in {where}" if where else "") +
                       " right now — prices here need a real mandi report, "
                       "so nothing is guessed"),
        }
    return result


@app.get("/market/status")
async def market_status():
    out = mandi_prices.status()
    # Backfill state for the AGMARKNET "district-wise wholesale prices monthly
    # analysis" report: how many states/crops/months are already stored.
    try:
        out["monthly"] = {"coverage": price_store.monthly_coverage(),
                          "top": price_store.monthly_state_summary(limit=12)}
    except Exception as exc:  # noqa: BLE001 - status must never 500
        out["monthly"] = {"error": str(exc)}
    return out


@app.get("/market/coverage")
async def market_coverage(commodity: Optional[str] = None, limit: int = 40):
    """
    How much REAL history exists, per commodity and market: first date, last
    date, observation count. This is what makes a forecast honest — the UI
    shows these numbers instead of promising accuracy it does not have.
    """
    limit = max(1, min(int(limit), 200))
    try:
        with price_store._connect() as conn:
            if commodity:
                resolved = mandi_prices.resolve_commodity(commodity) or commodity
                rows = conn.execute(
                    "SELECT commodity, market, district, state, "
                    "MIN(date) AS first_date, MAX(date) AS last_date, "
                    "COUNT(*) AS obs FROM mandi_prices WHERE commodity = ? "
                    "GROUP BY commodity, market, district, state "
                    "ORDER BY obs DESC LIMIT ?", (resolved, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT commodity, '' AS market, '' AS district, '' AS state, "
                    "MIN(date) AS first_date, MAX(date) AS last_date, "
                    "COUNT(*) AS obs FROM mandi_prices GROUP BY commodity "
                    "ORDER BY obs DESC LIMIT ?", (limit,),
                ).fetchall()
    except Exception as exc:  # noqa: BLE001 - empty store must not 500
        return {"commodity": commodity, "rows": [], "note": f"Store unavailable: {exc}"}

    data = [dict(r) for r in rows]
    return {
        "commodity": commodity,
        "rows": data,
        "total_rows": sum(int(r["obs"]) for r in data),
        "note": ("Counts are real AGMARKNET observations in the local store."
                 if data else "The price store is empty — run the daily ingest."),
    }


@app.get("/market/history")
async def market_history(commodity: str, district: Optional[str] = None,
                         state: Optional[str] = None, days: int = 90):
    """
    Real daily mandi price series (mean modal price across markets in scope)
    from the local price store, with the same commodity resolution as the
    forecast and a scope drill-down limited to district → its state. Only an
    unscoped (All-India) request may use the national series. Used to draw the
    crop-page price trend; when the store has nothing for the scope, `points`
    is empty and the frontend shows an honest message instead of a fabricated
    chart.
    """
    days = max(7, min(int(days), 365))
    resolved = mandi_prices.resolve_commodity(commodity) or commodity
    def _series(d, s):
        df = price_store.history(resolved, district=d, state=s,
                                 years=max(0.35, days / 365 * 1.4))
        if df is None or df.empty:
            return None
        g = (df.groupby("date")["modal_price"].mean()
               .round(1).reset_index())
        if g.empty:
            return None
        g = g.tail(days)
        return [{"date": r["date"].strftime("%Y-%m-%d"),"price": float(r["modal_price"])}
                for _, r in g.iterrows()]
    def _monthly_series(d, s):
        """Published AGMARKNET monthly averages — the 2-year history the
        forecast falls back to when no daily feed covers this scope."""
        df = price_store.monthly_history(resolved, district=d, state=s)
        if df is None or df.empty:
            return None
        return [{"date": r["date"].strftime("%Y-%m-%d"),
                 "price": round(float(r["price"]), 1)}
                for _, r in df.iterrows()]

    points = _series(district, state)
    scope, basis = ("district" if district else "state"), "daily"
    if not points and not state and district:
        state = price_store.state_for_district(district)  # resolve state from the district
        if state:
            points, scope = _series(None, state), "state"
    if not points and district and state:
        points, scope = _series(None, state), "state"
    # The chart must share the forecast's basis or the two lines never meet.
    # Use the forecast's own rule (60 daily observations over two years); a
    # "< 8 points in this window" test disagreed with it whenever a deep series
    # happened to have a recent gap.
    def _daily_days(d, s) -> int:
        df = price_store.history(resolved, district=d, state=s)
        return 0 if df is None or df.empty else int(df["date"].nunique())

    if points is not None and _daily_days(district, state) < price_forecast.MIN_OBS:
        monthly = _monthly_series(district, state) or (
            _monthly_series(None, state) if state else None)
        if monthly:
            points, basis = monthly, "monthly"
    if not points:
        points = _monthly_series(district, state)
        if points:
            basis = "monthly"
    if not points and state:
        points, scope, basis = _monthly_series(None, state), "state", "monthly"
    if not points and not district and not state:
        # Only an All-India request may use the national series: a Jharkhand
        # page must not draw a Tamil Nadu trend and call it local.
        points, scope = _series(None, None), "india"
        if not points:
            points, basis = _monthly_series(None, None), "monthly"
    if not points:
        return {"commodity": resolved, "district": district, "days": days,
                "points": [], "scope": scope, "basis": "none",
                "note": "No real mandi history for this scope yet — "
                        "accruing via daily ingestion and the monthly backfill."}
    return {
        "commodity": resolved,
        "district": district,
        "days": days,
        "scope": scope,
        "basis": basis,
        "points": points,
    }


@app.get("/weather")
async def weather(district: Optional[str] = None, state: Optional[str] = None,
                  lat: Optional[float] = None, lon: Optional[float] = None):
    """
    Live current weather for the resolved location (Open-Meteo). Used by
    HomeDashboard instead of a hardcoded card. Coordinates win over district
    names, matching /predict location resolution.
    """
    rlat, rlon = _resolve_coords(district, lat, lon, "auto", state=state)
    temp, humidity, rainfall, source = _weather_lookup(rlat, rlon)
    known = district_data.resolve_district(district, state, rlat, rlon)
    return {
        "district": (known or {}).get("district") or district,
        "state": (known or {}).get("state") or state,
        "temperature": round(float(temp), 1),
        "humidity": round(float(humidity), 1),
        "rainfall": round(float(rainfall), 1),
        "source": source,
    }


@app.get("/crop/info")
async def crop_information(crops: str):
    """Real agronomy (duration, yield, soil, pH/temp/rainfall ranges) for
    the requested crops, joined from the bundled crop master dataset and
    standard published references. Unknown crops come back flagged so the
    UI never substitutes fabricated defaults."""
    names = [c for c in (crops or "").split(",") if c.strip()]
    if not names:
        return {"crops": {}}
    return {"crops": crop_info.get_crop_info(names[:20])}


# ─────────────────────── Price prediction ────────────────────────────────

REAL_MODEL_LABEL = "mandi-forecast-v2"


def _forecast_entries(district: Optional[str], commodity: Optional[str],
                      market: Optional[str], days: int = 14,
                      state: Optional[str] = None,
                      lat: Optional[float] = None,
                      lon: Optional[float] = None) -> List[dict]:
    """Run the mandi forecast and shape it to the frontend contracts in
    priceApi.ts. Adds change_from_prev_pct so the daily table shows
    step-by-step movement.

    District coordinates are resolved so the live weather/disaster signals can
    reach the model; without them the forecast still runs, without triggers.
    """
    day = datetime.now().strftime("%Y-%m-%d")
    rlat, rlon = _resolve_coords(district, lat, lon, "auto", state=state)
    entries = price_forecast.forecast(
        district=district,
        commodity=commodity,
        market=market or "All",
        days=days,
        state=state,
        lat=rlat,
        lon=rlon,
    )
    for e in entries:
        e.setdefault("district", district or "")
        e.setdefault("market", market or "All")
        e["prediction_date"] = day
        e["scope_level"] = e.get("scope_level", "district")
        prev = e.get("current_price") or 0.0
        for pt in e.get("trajectory", []):
            if prev:
                pt["change_from_prev_pct"] = round(
                    (pt["predicted_price"] - prev) / prev * 100, 2)
            prev = pt["predicted_price"]
    return entries


def _forecast_or_404(district: Optional[str], commodity: Optional[str],
                     market: Optional[str], days: int = 14,
                     state: Optional[str] = None) -> List[dict]:
    entries = _forecast_entries(district, commodity, market, days, state=state)
    if not entries:
        where = ", ".join(p for p in (district, state) if p)
        raise HTTPException(
            status_code=404,
            detail=(f"Not enough real mandi history to forecast "
                    f"{commodity or 'this commodity'}"
                    + (f" in {where}" if where else "") +
                    " — a forecast here needs at least 60 daily mandi quotes or "
                    "12 published monthly averages, and the store has fewer for "
                    "this crop. Its current mandi price is still on the Market "
                    "page; the forecast appears once enough days are on record. "
                    "Data operator: run agmarknet_monthly.py to backfill the "
                    "published monthly averages for this crop."))
    return entries


def _price_guard():  # kept for /commodities + /markets backcompat
    if not price_engine.model_loaded():
        raise HTTPException(status_code=503,
                            detail=f"Price model unavailable: {price_engine.load_error()}")


@app.post("/predict/14day")
async def predict_14day(request: PricePredictionRequest):
    return _forecast_or_404(request.district, price_forecast.resolve_name(request.commodity),
                            request.market, state=request.state)


@app.post("/predict/trajectory")
async def predict_trajectory(request: PricePredictionRequest):
    return _forecast_or_404(request.district, price_forecast.resolve_name(request.commodity),
                            request.market, days=request.days, state=request.state)


@app.get("/predict/single")
async def single_prediction(district: str, commodity: str,
                            market: Optional[str] = "All",
                            state: Optional[str] = None):
    """Current market read derived from real data: latest observed price,
    forecast band and an honest confidence from backtest MAPE."""
    entry = _forecast_entries(
        district, price_forecast.resolve_name(commodity), market, state=state)
    if not entry:
        raise HTTPException(
            status_code=404, detail=f"No mandi data for {commodity} in {district}")
    e = entry[0]
    mape = e.get("mape", 8.0)
    confidence = round(max(50.0, min(95.0, 100.0 - mape * 2.0)), 1)
    month = datetime.now().strftime("%B")
    band_pct = (e["ci_high_14d"] - e["ci_low_14d"]) / max(e["predicted_price_14d"], 1) * 100
    supply = ("stable" if band_pct < 12
              else "watchful" if band_pct < 25 else "volatile")

    # Context factors (season, weather, flood risk, festivals, supply breadth)
    # computed from real inputs. The ones that can be calibrated on stored
    # prices (festivals, post-shock drift) already reached the forecast and are
    # reported back in `events`; the rest explain it without moving it.
    rlat, rlon = _resolve_coords(district, None, None, "auto", state=state)
    ctx = price_factors.build_factors(
        price_forecast.resolve_name(commodity), district,
        e.get("state"), rlat, rlon, e.get("predicted_change_pct"),
        season_index=e.get("season"))

    return {
        **{k: e.get(k) for k in ("district", "commodity", "market",
                                  "current_price", "predicted_price_14d",
                                  "predicted_change_pct")},
        "prediction_date": datetime.now().strftime("%Y-%m-%d"),
        "model": REAL_MODEL_LABEL,
        "model_used": e.get("model"),
        "model_label": e.get("model_label"),
        "model_scores": e.get("model_scores"),
        "events": e.get("events"),
        "data_quality": e.get("data_quality"),
        "confidence": confidence,
        "mape": mape,
        "history_last": e.get("history_last"),
        "stale_days": e.get("stale_days", 0),
        "signal": e.get("signal"),
        "history_basis": e.get("history_basis"),
        "season": e.get("season"),
        "festivals": e.get("festivals"),
        "shocks": e.get("shocks"),
        "factors": {
            # legacy flat keys kept for older clients
            "season": month,
            "supply_pressure": supply,
            "weather_impact": (
                "heavy rain risk" if ctx.get("weather", {}) and ctx["weather"]["flood_risk"]
                else "no flood signal" if ctx.get("weather") else "no coordinates"
            ),
            "festival_nearby": bool(ctx.get("festivals")),
            # full factor analysis
            "context": ctx,
        },
    }


@app.get("/predict/factors")
async def prediction_factors(commodity: str, district: Optional[str] = None,
                             state: Optional[str] = None,
                             lat: Optional[float] = None,
                             lon: Optional[float] = None):
    """Context factors around a forecast: seasonality, supply breadth, live
    weather (flood/heat risk) and the festival calendar. Each signal carries
    its own evidence; unavailable inputs are reported, never guessed."""
    name = price_forecast.resolve_name(commodity)
    rlat, rlon = _resolve_coords(district, lat, lon, "auto", state=state)
    change = None
    season = None
    entry = _forecast_entries(district, name, "All", state=state) if (district or state) else []
    if entry:
        change = entry[0].get("predicted_change_pct")
        season = entry[0].get("season")
    return price_factors.build_factors(name, district, state, rlat, rlon, change,
                                       season_index=season)


@app.get("/commodities")
async def get_commodities(district: Optional[str] = None,
                         state: Optional[str] = None,
                         predictable: bool = False,
                         strict: bool = False,
                         refresh: bool = False):
    """Commodity catalogue.

    Unscoped returns everything the store has ever seen. Scoped — the Market
    page — returns only what that district or state actually reported, so a
    farmer is never shown crops their mandi has never traded. `predictable=1`
    further keeps only crops with enough history to forecast. `refresh=1`
    re-asks the live feed instead of answering from the short-lived snapshot.
    """
    if district or state:
        return mandi_prices.scope_commodities(district, state, predictable,
                                              strict_district=strict,
                                              refresh=refresh)
    comms = price_forecast.known_commodities()
    fallback = price_engine.known_commodities() if price_engine.model_loaded() else []
    merged = sorted(set([c for c in comms if c] + [c for c in fallback if c]))
    return {"commodities": merged, "scope": "all"}


@app.get("/markets")
async def get_markets(district: Optional[str] = None,
                      state: Optional[str] = None,
                      refresh: bool = False):
    """Mandis in a district (or everywhere).

    `refresh=1` asks the live AGMARKNET feed for the district first: the store
    only knows mandis that have been ingested, which is why a district with a
    dozen active mandis showed three. The live rows are persisted, so a later
    call without network still lists them.
    """
    if district:
        # The snapshot is TTL-cached (90 s), so asking for it on every call
        # keeps the list current without re-hitting the feed per card.
        # `refresh=1` is the page's Refresh button: bypass that cache.
        names = mandi_prices.district_markets(district, state, refresh=refresh)
        if names:
            return {"markets": [{"district": district, "market": m}
                                for m in names]}
    markets = price_forecast.known_markets()
    out = []
    for m in markets:
        if district and (m.get("district") or "").lower() != district.lower():
            continue
        out.append({"district": m.get("district") or "",
                    "market": m.get("market") or ""})
    return {"markets": out}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
