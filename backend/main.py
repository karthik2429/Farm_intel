"""
FarmIntel Backend API Server

Serves ML models for crop recommendation, fertilizer recommendation,
crop rotation planning, and price prediction (Goa XGBoost + real weather).

Response shapes match the frontend contracts in src/lib/api.ts, priceApi.ts
and the page components (CropRotationPage, FertilizerRecommendationPage,
PricePredictionPage, HomeDashboard).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

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

app = FastAPI(title="FarmIntel API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    district: str = "North Goa"
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
        la, lo = get_lat_lon_from_district(district)
        if la is not None and lo is not None:
            return la, lo
    return lat, lon


def _weather_or_default(lat: Optional[float], lon: Optional[float]):
    """Live Open-Meteo weather with a monsoon-aware India fallback."""
    try:
        if lat is not None and lon is not None:
            temp, humidity, rainfall = get_weather(lat, lon)
            return float(temp), float(humidity), float(rainfall)
    except Exception:  # noqa: BLE001
        pass
    m = pd.Timestamp.now().month
    if m in (6, 7, 8, 9):
        return 27.0, 85.0, 12.0
    if m in (10, 11):
        return 28.0, 75.0, 3.0
    if m in (12, 1, 2):
        return 24.0, 60.0, 0.5
    return 31.0, 55.0, 1.0


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
    }


# ─────────────────────── Crop recommendation ─────────────────────────────

@app.post("/predict")
async def predict_crop(request: CropRecommendRequest):
    """
    District-aware crop recommendation.

    Blends the RandomForest ML model with the district's real soil survey
    (DES 2024-25), its historical cropping pattern and season. Falls back to
    pure ML when the district is unknown.

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
        result["soil_used"] = result.get("soil_used") or {
            "N": round(float(N), 1), "P": round(float(P), 1),
            "K": round(float(K), 1), "ph": round(float(ph), 1)}
        result["weather"] = {"temperature": round(temp, 1),
                             "humidity": round(hum, 1),
                             "rainfall": round(rain, 1)}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))

    results = result.get("results") or []
    if not results:
        raise HTTPException(status_code=503, detail="No recommendation available")

    ranked = [(r["crop"], float(r["display_score"])) for r in results]
    alternatives = [{"crop": c, "confidence": round(s, 4)}
                    for c, s in ranked[:4]]
    return {
        "crop": ranked[0][0],
        "confidence": round(ranked[0][1], 4),
        "alternatives": alternatives,
        "Top Crops": [[c, round(s, 4)] for c, s in ranked[:3]],
        "district": result.get("resolved_district"),
        "state": result.get("resolved_state"),
        "season": result.get("season"),
        "soil_used": result.get("soil_used"),
        "weather": result.get("weather"),
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


# ─────────────────────────── Mandi prices ────────────────────────────────

@app.get("/market/price")
async def market_price(commodity: str, district: Optional[str] = None,
                       state: Optional[str] = None):
    """
    Best-effort mandi price: Goa local history, bundled district snapshot,
    live AGMARKNET (self-healing probe), then MSP reference.

    Always answers 200 - when nothing is available the body carries
    `price: null` + `source: "unavailable"` so the frontend can render
    "--" without console 404 noise.
    """
    result = mandi_prices.get_price(commodity, district, state)
    if not result:
        return {
            "commodity": commodity,
            "district": district,
            "market": "",
            "price": None,
            "min_price": None,
            "max_price": None,
            "unit": "₹/quintal",
            "source": "unavailable",
            "detail": (f"No mandi price available for {commodity}"
                       + (f" in {district}" if district else "") + " right now"),
        }
    return result


@app.get("/market/status")
async def market_status():
    return mandi_prices.status()


@app.get("/market/history")
async def market_history(commodity: str, district: Optional[str] = None,
                         state: Optional[str] = None, days: int = 90):
    """
    Real daily mandi price series (mean modal price across markets in scope)
    from the local price store, with the same commodity resolution and
    scope drill-down as the forecast (district → state → India). Used to
    draw the crop-page price trend. When the store has nothing for the
    scope, `points` is empty and the frontend shows an honest message
    instead of a fabricated chart.
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
    points = _series(district, state)
    scope = "district"
    if not points and not state and district:
        state = price_store.state_for_district(district)  # resolve state from the district
        if state:
            points, scope = _series(None, state), "state"
    if not points and district and state:
        points, scope = _series(None, state), "state"
    if not points:
        points, scope = _series(None, None), "india"
    if not points:
        return {"commodity": resolved, "district": district, "days": days,
                "points": [], "scope": scope,
                "note": "No real mandi history for this scope yet — "
                        "accruing via daily ingestion."}
    return {
        "commodity": resolved,
        "district": district,
        "days": days,
        "scope": scope,
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
    temp, humidity, rainfall = _weather_or_default(rlat, rlon)
    known = district_data.resolve_district(district, state, rlat, rlon)
    return {
        "district": (known or {}).get("district") or district,
        "state": (known or {}).get("state") or state,
        "temperature": round(float(temp), 1),
        "humidity": round(float(humidity), 1),
        "rainfall": round(float(rainfall), 1),
        "source": "open_meteo" if (rlat is not None and rlon is not None)
                  else "national_fallback",
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

REAL_MODEL_LABEL = "holtwinters-mandi-v1"


def _forecast_entries(district: Optional[str], commodity: Optional[str],
                      market: Optional[str], days: int = 14) -> List[dict]:
    """Run the real Holt-Winters mandi forecast and shape it to the
    frontend contracts in priceApi.ts. Adds change_from_prev_pct so the
    daily table shows step-by-step movement."""
    day = datetime.now().strftime("%Y-%m-%d")
    entries = price_forecast.forecast(
        district=district,
        commodity=commodity,
        market=market or "All",
        days=days,
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
                     market: Optional[str], days: int = 14) -> List[dict]:
    entries = _forecast_entries(district, commodity, market, days)
    if not entries:
        raise HTTPException(
            status_code=404,
            detail=(f"Not enough real mandi history yet to forecast "
                    f"{commodity or 'this commodity'}"
                    + (f" in {district}" if district else "") +
                    ". Daily ingestion keeps accruing history — try again later."))
    return entries


def _price_guard():  # kept for /commodities + /markets backcompat
    if not price_engine.model_loaded():
        raise HTTPException(status_code=503,
                            detail=f"Price model unavailable: {price_engine.load_error()}")


@app.post("/predict/14day")
async def predict_14day(request: PricePredictionRequest):
    return _forecast_or_404(request.district, price_forecast.resolve_name(request.commodity),
                            request.market)


@app.post("/predict/trajectory")
async def predict_trajectory(request: PricePredictionRequest):
    return _forecast_or_404(request.district, price_forecast.resolve_name(request.commodity),
                            request.market, days=request.days)


@app.get("/predict/single")
async def single_prediction(district: str, commodity: str,
                            market: Optional[str] = "All"):
    """Current market read derived from real data: latest observed price,
    forecast band and an honest confidence from backtest MAPE."""
    entry = _forecast_entries(district, price_forecast.resolve_name(commodity), market)
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
    return {
        **{k: e.get(k) for k in ("district", "commodity", "market",
                                  "current_price", "predicted_price_14d",
                                  "predicted_change_pct")},
        "prediction_date": datetime.now().strftime("%Y-%m-%d"),
        "model": REAL_MODEL_LABEL,
        "confidence": confidence,
        "mape": mape,
        "history_last": e.get("history_last"),
        "stale_days": e.get("stale_days", 0),
        "signal": e.get("signal"),
        "factors": {
            "season": month,
            "supply_pressure": supply,
            "weather_impact": "not modelled in this phase",
            "festival_nearby": False,
        },
    }


@app.get("/commodities")
async def get_commodities():
    comms = price_forecast.known_commodities()
    fallback = price_engine.known_commodities() if price_engine.model_loaded() else []
    merged = sorted(set([c for c in comms if c] + [c for c in fallback if c]))
    return {"commodities": merged}


@app.get("/markets")
async def get_markets(district: Optional[str] = None):
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
