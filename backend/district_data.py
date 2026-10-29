"""
District intelligence layer for FarmIntel.

Data sources (all shipped with the project):
  * ../../soil_with_coordinates.csv  — DES district soil test data 2024-25
    (370 districts, 14 states) -> real N, P, K, pH and coordinates.
  * models/district_crop_map.json    — 355 districts -> crops actually
    grown there per season (kharif / rabi).
  * models/historical_lookup.json    — yield_score + area_share per
    district/season/crop.
  * FarmIntel_crop_master_v3_FIXED.xlsx — agronomic profiles (NPK targets,
    pH range, rainfall range, season) per crop.

The recommendation score for every candidate crop of a district is:

    0.50 * ml_prob   (RandomForest given NPK + live weather)
  + 0.30 * hist      (district historical yield/area performance)
  + 0.12 * soil_fit  (how close soil NPK/pH/rainfall are to crop targets)
  + 0.08 * ml_rank   (rank-position bonus from the pure ML ranking)

Crops that a district historically never grows are only shown if the ML
model is very confident about them (novel-crop suggestion).
"""

import os
import json
import difflib
from typing import Optional, Dict, List, Tuple

import numpy as np
import pandas as pd
import joblib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))  # "Capstone copy"

SOIL_CSV = os.path.join(PROJECT_ROOT, "soil_with_coordinates.csv")
MODELS_DIR = os.path.join(BASE_DIR, "models")
MASTER_XLSX = os.path.join(BASE_DIR, "FarmIntel_crop_master_v3_FIXED.xlsx")

# ---------------------------------------------------------------------------
# Load data once at import
# ---------------------------------------------------------------------------

_STOP_TOKENS = {"rural", "urban", "gramin"}

# Old -> official names (DES 2024-25 uses recently renamed districts)
_DISTRICT_ALIASES = {
    "nellore": "spsr nellore",
    "ysr kadapa": "y s r",
    "kadapa": "y s r",
    "ysr": "y s r",
    "ahmednagar": "ahilyanagar",
    "aurangabad maharashtra": "chhatrapati sambhajinagar",
    "osmanabad": "dharashiv",
    "hoshangabad": "narmadapuram",
    "khandwa": "khandwa east nimar",
    "khargone": "khargon west nimar",
    "belgaum": "belagavi",
    "bangalore rural": "bengaluru rural",
    "bangalore urban": "bengaluru urban",
    "bangalore": "bengaluru urban",
    "bellary": "ballari",
    "mysore": "mysuru",
    "tumkur": "tumakuru",
    "shimoga": "shivamogga",
    "gulbarga": "kalaburagi",
    "vijayanagara": "vijayanagar",
    "warangal rural": "warangal",
    "warangal urban": "warangal",
    "komaram bheem": "komaram bheem asifabad",
    "jayashankar bhupalpally": "bhupalpally",
    "mohali": "sahibzada ajit singh nagar",
    "fatehgarh sahib": "fatehgarh sahib",
    "west champaran": "paschim champaran",
    "east champaran": "purbi champaran",
    "allahabad": "prayagraj",
}


def _norm(s) -> str:
    """Normalise a state/district/crop name for matching."""
    out = str(s).strip().lower()
    for ch in ("\u2013", "\u2014", "-", "_", "(", ")", ".", ","):
        out = out.replace(ch, " ")
    return " ".join(out.split())


def _alias(name: str) -> str:
    n = _norm(name)
    n_no_stop = " ".join(t for t in n.split() if t not in _STOP_TOKENS)
    return _DISTRICT_ALIASES.get(n, _DISTRICT_ALIASES.get(n_no_stop, n_no_stop))


def _safe_share(high, parts) -> float:
    total = sum(float(x) for x in parts)
    return float(high) / total if total > 0 else 0.0


def _share_to_ppm(high, medium, low, scale: float = 1.0) -> float:
    """Convert category sample-shares into an indicative kg/ha-style value."""
    vals = [high, medium, low]
    if any(v is None or (isinstance(v, float) and np.isnan(float(v))) for v in vals):
        return 0.0
    high, medium, low = float(high), float(medium), float(low)
    total = high + medium + low
    if total <= 0:
        return 0.0
    # Dominant category drives the level; blends soften hard edges.
    share = (high * 1.0 + medium * 0.55 + low * 0.15) / total
    return round(max(8.0, min(280.0, share * 280.0 * scale)), 1)


def _ph_from_shares(acidic, neutral, alkaline) -> float:
    vals = [acidic, neutral, alkaline]
    if any(v is None or (isinstance(v, float) and np.isnan(float(v))) for v in vals):
        return 6.5
    acidic, neutral, alkaline = float(acidic), float(neutral), float(alkaline)
    total = acidic + neutral + alkaline
    if total <= 0:
        return 6.5
    share = (acidic * 5.8 + neutral * 6.8 + alkaline * 8.2) / total
    return round(float(np.clip(share, 4.5, 9.5)), 1)


def _profile_from_row(r) -> dict:
    return {
        "state": r["state"],
        "lat": float(r["latitude"]),
        "lon": float(r["longitude"]),
        "N": _share_to_ppm(r.get("n_high", 0), r.get("n_medium", 0),
                           r.get("n_low", 0)),
        "P": _share_to_ppm(r.get("p_high", 0), r.get("p_medium", 0),
                           r.get("p_low", 0), scale=0.55),
        "K": _share_to_ppm(r.get("k_high", 0), r.get("k_medium", 0),
                           r.get("k_low", 0), scale=1.25),
        "ph": _ph_from_shares(r.get("ph_acidic", 0), r.get("ph_neutral", 0),
                              r.get("ph_alkaline", 0)),
    }


try:
    _soil_df = pd.read_csv(SOIL_CSV)
    for col in ("state", "district"):
        _soil_df[col] = _soil_df[col].astype(str).map(_norm)
    # Average scheme-level nutrient sample counts into one profile/district
    _soil_df["scheme"] = _soil_df["scheme"].fillna("All")
    group_cols = ["state", "district", "latitude", "longitude"]
    agg = _soil_df.groupby(group_cols, as_index=False)[
        [c for c in _soil_df.columns
         if c.startswith(("n_", "p_", "k_", "ph_", "oc_", "s_"))]
    ].mean()
    SOIL_PROFILES: Dict[str, dict] = {}      # name -> profile (unique names)
    SOIL_PROFILE_INDEX: Dict[str, list] = {} # name -> [profiles] (all states)
    for _, r in agg.iterrows():
        prof = _profile_from_row(r)
        SOIL_PROFILES[r["district"]] = prof
        SOIL_PROFILE_INDEX.setdefault(r["district"], []).append(prof)
except Exception as e:  # noqa: BLE001
    print(f"[district_data] soil CSV load failed: {e}")
    SOIL_PROFILES = {}
    SOIL_PROFILE_INDEX = {}


try:
    with open(os.path.join(MODELS_DIR, "district_crop_map.json")) as f:
        DISTRICT_CROP_MAP: Dict[str, dict] = {
            _alias(k): v for k, v in json.load(f).items()}
    with open(os.path.join(MODELS_DIR, "historical_lookup.json")) as f:
        HISTORICAL_LOOKUP: Dict[str, dict] = {
            _alias(k): v for k, v in json.load(f).items()}
except Exception as e:  # noqa: BLE001
    print(f"[district_data] crop map load failed: {e}")
    DISTRICT_CROP_MAP, HISTORICAL_LOOKUP = {}, {}

try:
    _master = pd.read_excel(MASTER_XLSX, engine="openpyxl")
    _master["crop_lc"] = _master["crop"].astype(str).str.lower().str.strip()
    _master["season_lc"] = _master["season"].astype(str).str.lower().str.strip()
    MASTER_CROPS: Dict[str, dict] = {}
    for _, r in _master.iterrows():
        MASTER_CROPS.setdefault(r["crop_lc"], {
            "season": r["season_lc"],
            "N": float(r["N"]), "P": float(r["P"]), "K": float(r["K"]),
            "ph_min": float(r["ph_min"]), "ph_max": float(r["ph_max"]),
            "rain_min": float(r["rainfall_min"]), "rain_max": float(r["rainfall_max"]),
            "temp_min": float(r["temp_min"]), "temp_max": float(r["temp_max"]),
        })
except Exception as e:  # noqa: BLE001
    print(f"[district_data] master xlsx load failed: {e}")
    MASTER_CROPS = {}

# ML model (same artifacts main.py loads)
try:
    ML_MODEL = joblib.load(os.path.join(MODELS_DIR, "rf_model.pkl"))
    ML_LE = joblib.load(os.path.join(MODELS_DIR, "label_encoder.pkl"))
except Exception as e:  # noqa: BLE001
    print(f"[district_data] RF model load failed: {e}")
    ML_MODEL, ML_LE = None, None

# Friendly display names for the coarse government crop categories
CATEGORY_DISPLAY = {
    "shree anna /nutri cereals": "Shree Anna (Millets)",
    "nutri/coarse cereals": "Nutri/Coarse Cereals",
    "total food grains": "Food Grains",
    "cereals": "Cereals",
    "other pulses": "Other Pulses",
    "small millets": "Small Millets",
    "jowar": "Jowar (Sorghum)",
    "bajra": "Bajra (Pearl Millet)",
    "ragi": "Ragi (Finger Millet)",
    "tur": "Tur (Pigeon Pea)",
    "urad": "Urad (Black Gram)",
    "moong": "Moong (Green Gram)",
    "gram": "Gram (Chickpea)",
    "maize": "Maize", "rice": "Rice", "wheat": "Wheat", "barley": "Barley",
    "lentil": "Lentil (Masoor)",
}

# Government aggregate buckets - not real crops a farmer can sow
_AGGREGATE_CATEGORIES = {
    "total food grains", "cereals", "nutri/coarse cereals",
    "shree anna /nutri cereals", "other pulses",
}

# ---------------------------------------------------------------------------
# Geocoding (for districts outside the soil dataset)
# ---------------------------------------------------------------------------

_GEO_CACHE: Dict[str, Optional[Tuple[float, float]]] = {}
_GEOLOCATOR = None


def _get_geolocator():
    global _GEOLOCATOR
    if _GEOLOCATOR is None:
        try:
            from geopy.geocoders import Nominatim
            _GEOLOCATOR = Nominatim(user_agent="farmintel-crop-app/1.0")
        except Exception:  # noqa: BLE001
            return None
    return _GEOLOCATOR


def geocode_district(district: str, state: Optional[str] = None,
                     timeout: float = 4.0) -> Optional[Tuple[float, float]]:
    """Geocode a district to (lat, lon); cached; never raises."""
    key = f"{_norm(district)}|{_norm(state) if state else ''}"
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    geo = None
    locator = _get_geolocator()
    if locator is not None:
        query = f"{district} district, {state}, India" if state else f"{district} district, India"
        try:
            loc = locator.geocode(query, timeout=timeout)
            if loc:
                geo = (float(loc.latitude), float(loc.longitude))
        except Exception:  # noqa: BLE001
            geo = None
    _GEO_CACHE[key] = geo
    return geo


def _pick_profile(name: str, state: Optional[str]) -> Optional[Tuple[str, dict]]:
    """Choose the right profile for a resolved district name."""
    profs = SOIL_PROFILE_INDEX.get(name) or ([SOIL_PROFILES[name]]
                                             if name in SOIL_PROFILES else [])
    if not profs:
        return None
    if len(profs) == 1:
        return name, profs[0]
    if state:
        s = _norm(state)
        for p in profs:
            if p["state"] == s:
                return name, p
    return name, profs[0]


def resolve_district(district: Optional[str], state: Optional[str] = None,
                     lat: Optional[float] = None,
                     lon: Optional[float] = None) -> Optional[dict]:
    """
    Resolve a location to a known district profile. Order:
      1. exact / alias / fuzzy / token district-name match
         (state disambiguates same-name districts)
      2. nearest soil profile by coordinates
    Returns {district, state, lat, lon, soil{N,P,K,ph}} or None.
    """
    if district:
        wanted = _alias(district)
        # exact (alias-applied)
        hit = _pick_profile(wanted, state)
        if hit:
            return _pack(*hit)
        # raw exact (unaliased, e.g. multi-word official names)
        hit = _pick_profile(_norm(district), state)
        if hit:
            return _pack(*hit)
        # fuzzy over alias-applied names
        names = list({n for n in list(SOIL_PROFILE_INDEX)
                      + [_alias(n) for n in SOIL_PROFILE_INDEX]})
        close = difflib.get_close_matches(wanted, names, n=1, cutoff=0.85)
        if close:
            hit = _pick_profile(close[0], state)
            if hit:
                return _pack(*hit)
        # token containment: 'komaram bheem' ⊂ 'komaram bheem asifabad'
        toks = set(wanted.split())
        if toks:
            for n in names:
                if toks and toks.issubset(set(n.split())):
                    hit = _pick_profile(n, state)
                    if hit:
                        return _pack(*hit)
    # coordinate match (also used for "Use current location")
    if lat is not None and lon is not None and SOIL_PROFILES:
        best, best_d = None, float("inf")
        for name, prof in SOIL_PROFILES.items():
            dd = (prof["lat"] - lat) ** 2 + (prof["lon"] - lon) ** 2
            if dd < best_d:
                best, best_d = name, dd
        if best is not None and best_d < 1.5:  # ~120 km guard
            return _pack(best, SOIL_PROFILES[best])
    # 4) geocode the name so ML still gets real local weather + coords
    if district:
        geo = geocode_district(district, state)
        if geo:
            return {
                "district": _norm(district), "state": _norm(state) if state else None,
                "lat": geo[0], "lon": geo[1], "soil": None,
            }
    return None


def _pack(name: str, prof: dict) -> dict:
    return {
        "district": name,
        "state": prof.get("state"),
        "lat": prof.get("lat"),
        "lon": prof.get("lon"),
        "soil": {"N": prof.get("N"), "P": prof.get("P"),
                 "K": prof.get("K"), "ph": prof.get("ph")},
    }


def district_names_for_state(state: str) -> List[str]:
    s = _norm(state)
    return sorted({d for d, p in SOIL_PROFILES.items() if p["state"] == s})


def default_soil_for(district: Optional[str], state: Optional[str],
                     lat: Optional[float], lon: Optional[float]) -> Optional[dict]:
    loc = resolve_district(district, state, lat, lon)
    if not loc:
        return None
    return {
        "district": loc["district"],
        "state": loc["state"],
        "N": loc["soil"]["N"], "P": loc["soil"]["P"],
        "K": loc["soil"]["K"], "ph": loc["soil"]["ph"],
        "lat": loc["lat"], "lon": loc["lon"],
    }


# ---------------------------------------------------------------------------
# District + season aware scoring
# ---------------------------------------------------------------------------

# Aliases: government crop-map names / master-xlsx names -> RF label classes
_CROP_ALIASES = {
    "gram": "chickpea", "chickpea": "chickpea",
    "tur": "pigeonpeas", "pigeon pea": "pigeonpeas",
    "arhar": "pigeonpeas",
    "urad": "blackgram", "black gram": "blackgram", "blackgram": "blackgram",
    "moong": "mungbean", "green gram": "mungbean", "mungbean": "mungbean",
    "lentil": "lentil", "masoor": "lentil",
    "rice": "rice", "paddy": "rice",
    "maize": "maize", "makka": "maize",
    "wheat": "wheat", "barley": "barley", "jau": "barley",
    "jowar": "jowar", "sorghum": "jowar",
    "bajra": "bajra", "pearl millet": "bajra",
    "ragi": "ragi", "finger millet": "ragi",
    "cotton": "cotton", "kapas": "cotton",
    "groundnut": "groundnut", "peanut": "groundnut",
    "sugarcane": "sugarcane", "banana": "banana", "mango": "mango",
    "grapes": "grapes", "orange": "orange", "papaya": "papaya",
    "pomegranate": "pomegranate", "muskmelon": "muskmelon",
    "watermelon": "watermelon", "coffee": "coffee", "jute": "jute",
    "kidney bean": "kidneybeans", "kidneybeans": "kidneybeans",
    "moth bean": "mothbeans", "mothbeans": "mothbeans",
    "millet": "bajra", "small millets": "ragi",
    "shree anna /nutri cereals": "bajra", "nutri/coarse cereals": "maize",
    "cereals": "maize", "total food grains": "rice",
    "other pulses": "chickpea",
}


def _ml_label(crop_name: str) -> Optional[str]:
    key = _norm(crop_name)
    alias = _CROP_ALIASES.get(key)
    if alias and ML_LE is not None and alias in ML_LE.classes_:
        return alias
    if ML_LE is not None and key in ML_LE.classes_:
        return key
    return None


def _season_key_for_state(state: Optional[str], season: str) -> str:
    """Map the UI season onto the dataset season key.

    The historical crop dataset only tracks kharif / rabi. Kerala and Tamil
    Nadu farm year-round, so their rows live under "whole" - map the UI's
    kharif/rabi picks onto whichever season key the state actually has data
    for, so these states never collapse to a bare ML ranking.
    """
    s = _norm(state or "")
    if s in {"kerala", "tamil nadu", "andaman and nicobar", "ladakh"}:
        return "whole"
    return season if season in {"kharif", "rabi"} else "kharif"


def _state_hist_candidates(state: Optional[str], season_key: str,
                           exclude: set) -> List[Tuple[str, float]]:
    """Crops proven across the state, ranked by how many districts grow them.

    Used when a district itself has no season-specific crop rows (e.g.
    Bengaluru Urban, Karnal, Rajkot). Much better than a bare ML ranking:
    these are crops agriculture ministry data says are actually grown in
    this state, so results stay regionally sensible.
    """
    if not state:
        return []
    s = _norm(state)
    tally: Dict[str, int] = {}
    for dname, seasons in DISTRICT_CROP_MAP.items():
        prof = (SOIL_PROFILE_INDEX.get(dname) or [None])[0]
        if prof is None or (prof.get("state") or "") != s:
            continue
        for c in (seasons or {}).get(season_key, []) or []:
            if c in _AGGREGATE_CATEGORIES:
                continue
            tally[c] = tally.get(c, 0) + 1
    ranked = sorted(tally.items(), key=lambda x: x[1], reverse=True)
    out = [(c, min(0.95, 0.55 + 0.08 * n)) for c, n in ranked
           if c not in exclude][:10]
    if out:
        return out
    # State not covered by the historical crop map at all (the map only
    # tracks the 14 DES soil-survey states) - use curated dominant-crop
    # lists so Haryana/Gujarat/Kerala/TN/WB/Odisha districts stay on
    # regionally sensible staples instead of a bare ML guess.
    fb = _STATE_FALLBACK_CROPS.get(s, {})
    fallback = fb.get(season_key if season_key in ("kharif", "rabi")
                      else "kharif") or []
    return [(c, 0.75 if i < 2 else 0.6) for i, c in enumerate(fallback)
            if c not in exclude]


# States the district crop map doesn't cover -> dominant crops per season
# (ministry-of-agriculture cropping pattern, coarse). Keeps recommendations
# regionally sensible for Haryana/Gujarat/Kerala/TN/WB/Odisha districts.
_STATE_FALLBACK_CROPS = {
    "haryana": {
        "kharif": ["rice", "bajra", "cotton", "maize", "jowar", "moong", "tur"],
        "rabi": ["wheat", "mustard", "gram", "barley", "urad"],
    },
    "gujarat": {
        "kharif": ["cotton", "groundnut", "bajra", "maize", "rice", "moong"],
        "rabi": ["wheat", "gram", "mustard", "barley"],
    },
    "tamil nadu": {
        "kharif": ["rice", "maize", "cotton", "groundnut", "jowar", "tur", "urad"],
        "rabi": ["rice", "maize", "gram", "urad", "groundnut"],
    },
    "kerala": {
        "kharif": ["rice", "maize", "groundnut"],
        "rabi": ["rice", "maize", "gram"],
    },
    "west bengal": {
        "kharif": ["rice", "maize", "jute", "urad", "moong", "tur"],
        "rabi": ["rice", "wheat", "mustard", "gram"],
    },
    "odisha": {
        "kharif": ["rice", "maize", "jowar", "bajra", "tur", "moong",
                   "groundnut", "urad"],
        "rabi": ["rice", "wheat", "gram", "mustard", "urad"],
    },
}


def _score_candidates(
    N: float, P: float, K: float, ph: float,
    temperature: float, humidity: float, rainfall: float,
    candidates: List[Tuple[str, float]],
    hist: Dict[str, dict],
    loc: dict,
    season: str,
    top_n: int,
    state_fallback: bool = False,
) -> dict:
    """Rank candidate crops with ML probability, historical yield/area,
    soil fit and provenance prior - shared by the district path and the
    state-merge path."""
    master = MASTER_CROPS
    soil = loc.get("soil")
    soil_valid = bool(soil) and any(
        (soil.get(k) or 0) > 0 for k in ("N", "P", "K"))

    ml_probs: Dict[str, float] = {}
    if ML_MODEL is not None and ML_LE is not None:
        try:
            feats = np.array([[N, P, K, temperature, humidity, ph, rainfall]])
            probas = ML_MODEL.predict_proba(feats)[0]
            ml_probs = dict(zip(ML_LE.classes_, probas))
        except Exception as e:  # noqa: BLE001
            print(f"[district_data] ML predict failed: {e}")

    results = []
    for crop_name, prior in candidates:
        ml_label = _ml_label(crop_name)
        p_ml = float(ml_probs.get(ml_label, 0.0)) if ml_label else 0.0
        h = hist.get(crop_name, {})
        yield_s = float(h.get("yield_score", 0) or 0)
        area_s = float(h.get("area_share", 0) or 0)
        hist_score = (0.55 * yield_s + 0.45 * area_s) * prior

        prof = master.get(crop_name)
        if prof and soil_valid:
            soil_fit = _soil_fit(soil["N"], soil["P"], soil["K"], soil["ph"],
                                 prof, rainfall)
        else:
            soil_fit = 0.5

        if state_fallback:
            # No district history backs these candidates, so lean on the
            # curated prior + agronomic fit instead of letting a single
            # strong ML class dominate.
            final = (0.45 * p_ml + 0.25 * hist_score + 0.15 * soil_fit
                     + 0.15 * prior)
        else:
            final = (0.50 * p_ml + 0.30 * hist_score + 0.12 * soil_fit
                     + 0.08 * prior)
        results.append({
            "crop": CATEGORY_DISPLAY.get(crop_name, crop_name.title()),
            "raw_crop": crop_name,
            "ml_label": ml_label,
            "ml_prob": round(p_ml, 4),
            "hist_score": round(float(hist_score), 3),
            "soil_fit": round(float(soil_fit), 3),
            "final_score": round(float(final), 4),
        })

    results.sort(key=lambda x: x["final_score"], reverse=True)

    # Commercial crops (cotton, coffee, sugarcane...): the gov crop map
    # only tracks food grains so they never make the candidate list. They
    # may only FILL REMAINING SLOTS below the district's own staples -
    # never displace them (a Karnataka district must not show coffee ahead
    # of its actual rice/jowar/ragi).
    if ml_probs and len(results) < top_n:
        covered = {r["ml_label"] for r in results if r["ml_label"]}
        floor = float(results[-1]["final_score"]) if results else 0.0
        aff = _STATE_CROP_AFFINITY.get(loc.get("state") or "", {})
        commercial = [
            (lbl, float(p)) for lbl, p in ml_probs.items()
            if lbl not in covered and lbl in _COMMERCIAL_ML_CROPS
            and (aff.get(lbl, 0.0) >= 0.4 or p >= 0.15)
        ]
        scored = []
        for lbl, p in commercial:
            a = aff.get(lbl, 0.0)
            prof = master.get(lbl)
            if prof and soil_valid:
                sf = _soil_fit(soil["N"], soil["P"], soil["K"], soil["ph"],
                               prof, rainfall)
            else:
                sf = 0.5
            raw = 0.4 * p + 0.5 * a + 0.1 * sf
            scored.append((lbl, p, sf, min(raw, floor * 0.9)))
        scored.sort(key=lambda x: x[3], reverse=True)
        for lbl, p, sf, fin in scored[: top_n - len(results)]:
            results.append({
                "crop": CATEGORY_DISPLAY.get(lbl, lbl.title()),
                "raw_crop": lbl,
                "ml_label": lbl, "ml_prob": round(p, 4),
                "hist_score": 0.0, "soil_fit": round(float(sf), 3),
                "final_score": round(float(fin), 4),
                "novel": True,
                "basis": "state cropping pattern + ML",
            })
        results.sort(key=lambda x: x["final_score"], reverse=True)

    # Novel-crop suggestions: strong ML picks the district rarely grows.
    # Only fill remaining slots and always ranked below proven district
    # crops. Skipped in state-fallback mode: those candidates are already
    # the state's proven crops and a hot ML class (muskmelon!) must not
    # leapfrog them.
    if ml_probs and not state_fallback and not any(r.get("novel") for r in results):
        viable = [r for r in results
                  if r["final_score"] > 0.15 or (r["ml_prob"] or 0) > 0.10]
        grown = {r["ml_label"] for r in viable if r["ml_label"]}
        if len(viable) < 3:
            novel = [(n, float(p)) for n, p in ml_probs.items()
                     if p >= 0.30 and n not in grown]
            novel.sort(key=lambda x: x[1], reverse=True)
            for name, p in novel[: 3 - len(viable)]:
                results.append({
                    "crop": name.title(), "raw_crop": name,
                    "ml_label": name, "ml_prob": round(p, 4),
                    "hist_score": 0.0, "soil_fit": 0.5,
                    "final_score": round(0.5 * p + 0.04, 4),
                    "novel": True,
                })
            results.sort(key=lambda x: x["final_score"], reverse=True)

    results = results[:max(top_n, 3)]

    # Confidence rescale so the top crop shows a believable % match
    top = float(results[0]["final_score"]) if results else 0.0
    scale = (1.0 / top) if top > 0 else 1.0
    display_scores = []
    for r in results:
        ds = min(0.97, max(0.35, float(r["final_score"]) * scale))
        display_scores.append(round(ds, 4))

    return {
        "resolved_district": loc.get("district"),
        "resolved_state": loc.get("state"),
        "soil_used": soil,
        "season": season,
        "top": results[0]["crop"] if results else None,
        "results": [
            {**r, "display_score": ds} for r, ds in zip(results, display_scores)
        ],
    }


def _state_hint(lat: Optional[float], lon: Optional[float],
                state: Optional[str]) -> Optional[str]:
    """Best state name for a GPS-only request: explicit state, else reverse
    geocode the coordinates, else None (pure ML)."""
    if state:
        return _norm(state)
    if lat is None or lon is None:
        return None
    return reverse_state(lat, lon)


def reverse_state(lat: float, lon: float, timeout: float = 4.0) -> Optional[str]:
    """Reverse geocode (lat, lon) -> normalised state name; cached."""
    key = ("rev", round(lat, 2), round(lon, 2))
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    st = None
    locator = _get_geolocator()
    if locator is not None:
        try:
            loc = locator.reverse((lat, lon), timeout=timeout)
            addr = (getattr(loc, "raw", {}) or {}).get("address", {}) if loc else {}
            if addr.get("state"):
                st = _norm(addr["state"])
        except Exception:  # noqa: BLE001
            st = None
    _GEO_CACHE[key] = st
    return st


def recommend_for_district(
    N: float, P: float, K: float, ph: float,
    temperature: float, humidity: float, rainfall: float,
    district: Optional[str] = None,
    state: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    season: str = "kharif",
    top_n: int = 5,
) -> dict:
    """
    Full district-aware recommendation.

    Candidate priority:
      1. the district's own season crop list + historical yields
      2. same-state crops proven in other districts (state historical merge)
      3. strong ML-only suggestions
    A bare ML ranking is the last resort (district fully unknown).
    """
    season = (season or "kharif").strip().lower()
    loc = resolve_district(district, state, lat, lon)

    if loc is None or not loc.get("soil"):
        # District unknown OR no soil survey rows (e.g. Kerala/TN districts):
        # try the state's own cropping pattern first (crop map covers states
        # the soil survey doesn't, e.g. Kerala/TN/Gujarat/Haryana), then
        # fall back to pure ML; weather already reflects the real location.
        out = None
        st = _state_hint(lat, lon, state)
        if st:
            sk = _season_key_for_state(st, season)
            state_cands = _state_hist_candidates(st, sk, exclude=set())
            if state_cands:
                loc_for_score = loc or {
                    "district": _norm(district) if district else None,
                    "state": _norm(st), "lat": None, "lon": None,
                    "soil": None,
                }
                out = _score_candidates(
                    N, P, K, ph, temperature, humidity, rainfall,
                    state_cands, HISTORICAL_LOOKUP.get(loc_for_score["district"], {})
                    .get(sk, {}), loc_for_score, season, top_n,
                    state_fallback=True)
                out["note"] = ("no district soil data - ranked by "
                                f"{st} cropping pattern + climate ML")
        if out is None:
            out = _pure_ml(N, P, K, ph, temperature, humidity, rainfall, top_n)
            if loc is not None:
                out["resolved_district"] = loc.get("district")
                out["resolved_state"] = loc.get("state")
                out["note"] = "no district soil data - climate-driven ML ranking"
        else:
            out["resolved_district"] = (loc or {}).get("district")
            out["resolved_state"] = (loc or {}).get("state") or _norm(st)
        return out

    d = loc["district"]
    season_key = _season_key_for_state(loc.get("state"), season)
    allowed_raw = DISTRICT_CROP_MAP.get(d, {}).get(season_key) or []
    hist = HISTORICAL_LOOKUP.get(d, {}).get(season_key, {})
    master = MASTER_CROPS

    # Build the candidate list: district's own crops first (specific crops
    # only - skip aggregate buckets like "Total Food Grains")
    candidates: List[Tuple[str, float]] = []  # (crop_name, hist_prior)
    for c in allowed_raw:
        if c in _AGGREGATE_CATEGORIES:
            continue
        if hist.get(c, {}).get("area_share", 0) > 0 or hist.get(c, {}).get("yield_score", 0) > 0:
            candidates.append((c, 1.0))
        else:
            candidates.append((c, 0.55))
    if len(candidates) < 4:
        # Thin or empty district list (e.g. Bengaluru Urban kharif, districts
        # tracked only under the other season): merge in crops proven across
        # the same state so the ranking stays location-specific instead of
        # collapsing to a random ML guess.
        have = {c for c, _ in candidates}
        for c, prior in _state_hist_candidates(
                loc.get("state"), season_key, exclude=have):
            candidates.append((c, prior * 0.85))
    if not candidates:
        # unknown district-season combo: use historical keys as candidates
        candidates = [(c, 0.8) for c in hist.keys()]
        if not candidates:
            return _pure_ml(N, P, K, ph, temperature, humidity, rainfall, top_n)

    return _score_candidates(
        N, P, K, ph, temperature, humidity, rainfall,
        candidates, hist, loc, season, top_n)


# RF classes with dedicated district-history coverage vs commercial crops
# that the gov crop map doesn't track (they surface via ML strength only).
_COMMERCIAL_ML_CROPS = {
    "cotton", "coffee", "sugarcane", "jute", "coconut", "banana",
    "mango", "grapes", "orange", "papaya", "pomegranate", "apple",
}

# State-level cropping-pattern affinity for commercial crops (0..1).
# The gov crop map only tracks food grains, so without this the UI can
# never recommend cotton/coffee/sugarcane. Values reflect where these
# crops are actually grown at scale in India.
_STATE_CROP_AFFINITY = {
    "karnataka": {"coffee": 0.85, "sugarcane": 0.7, "cotton": 0.6,
                  "grapes": 0.6, "coconut": 0.5, "banana": 0.45,
                  "mango": 0.45, "pomegranate": 0.5},
    "andhra pradesh": {"cotton": 0.7, "mango": 0.7, "coconut": 0.6,
                       "banana": 0.55, "papaya": 0.45, "sugarcane": 0.5},
    "telangana": {"cotton": 0.8, "mango": 0.55, "papaya": 0.5,
                  "banana": 0.45, "sugarcane": 0.4},
    "maharashtra": {"cotton": 0.85, "sugarcane": 0.8, "grapes": 0.7,
                    "orange": 0.65, "banana": 0.55, "pomegranate": 0.6},
    "madhya pradesh": {"cotton": 0.6, "orange": 0.5, "mango": 0.45,
                       "pomegranate": 0.4},
    "punjab": {"cotton": 0.6, "sugarcane": 0.4},
    "haryana": {"cotton": 0.6, "sugarcane": 0.4},
    "rajasthan": {"cotton": 0.45, "pomegranate": 0.4},
    "gujarat": {"cotton": 0.8, "mango": 0.4, "papaya": 0.4,
                "banana": 0.4, "pomegranate": 0.5},
    "tamil nadu": {"coconut": 0.8, "sugarcane": 0.7, "banana": 0.6,
                   "coffee": 0.5, "mango": 0.5, "cotton": 0.4},
    "kerala": {"coconut": 0.9, "coffee": 0.7, "banana": 0.55,
               "mango": 0.4, "papaya": 0.45},
    "uttar pradesh": {"sugarcane": 0.85, "mango": 0.5, "papaya": 0.4},
    "bihar": {"mango": 0.5, "sugarcane": 0.45, "banana": 0.45},
    "west bengal": {"jute": 0.9, "mango": 0.45, "banana": 0.4,
                    "coconut": 0.35},
    "odisha": {"mango": 0.45, "coconut": 0.5, "banana": 0.4},
    "jharkhand": {"mango": 0.45},
    "uttarakhand": {"sugarcane": 0.4, "mango": 0.35},
    "himachal pradesh": {"apple": 0.9},
    "tripura": {"jute": 0.4, "banana": 0.5, "mango": 0.35},
    "goa": {"coconut": 0.8, "mango": 0.6, "banana": 0.5},
}


def _soil_fit(n, p, k, ph, prof: dict, rainfall: float) -> float:
    """0..1 fit of the district's real soil to a crop's agronomic profile."""
    # NPK: closeness of soil supply to crop requirement
    n_fit = 1.0 - min(1.0, abs(n - prof["N"]) / max(prof["N"], 40.0))
    p_fit = 1.0 - min(1.0, abs(p - prof["P"]) / max(prof["P"], 25.0))
    k_fit = 1.0 - min(1.0, abs(k - prof["K"]) / max(prof["K"], 25.0))
    npk_fit = (n_fit + p_fit + k_fit) / 3.0
    # pH window
    if prof["ph_min"] <= ph <= prof["ph_max"]:
        ph_fit = 1.0
    else:
        dist = min(abs(ph - prof["ph_min"]), abs(ph - prof["ph_max"]))
        ph_fit = max(0.0, 1.0 - dist / 1.5)
    # rainfall window (use annualised assumption: monthly mm * 12 is too
    # aggressive; treat live monthly rainfall as seasonal indicator)
    season_rain = rainfall * 12  # rough annualisation of current month
    if season_rain <= prof["rain_min"]:
        rain_fit = max(0.2, 1.0 - (prof["rain_min"] - season_rain) / prof["rain_min"])
    elif season_rain >= prof["rain_max"]:
        rain_fit = max(0.2, 1.0 - (season_rain - prof["rain_max"]) / prof["rain_max"])
    else:
        rain_fit = 1.0
    return float(np.clip(0.45 * npk_fit + 0.35 * ph_fit + 0.20 * rain_fit, 0.0, 1.0))


def _pure_ml(N, P, K, ph, temperature, humidity, rainfall, top_n) -> dict:
    """District unknown -> plain RandomForest ranking (old behaviour)."""
    results = []
    if ML_MODEL is not None and ML_LE is not None:
        try:
            feats = np.array([[N, P, K, temperature, humidity, ph, rainfall]])
            probas = ML_MODEL.predict_proba(feats)[0]
            ranked = sorted(zip(ML_LE.classes_, probas),
                            key=lambda x: x[1], reverse=True)[:top_n]
            results = [{
                "crop": c.title(), "raw_crop": c, "ml_label": c,
                "ml_prob": round(float(p), 4), "hist_score": 0.0,
                "soil_fit": 0.5, "final_score": round(float(p), 4),
                "display_score": round(min(0.97, float(p)), 4),
            } for c, p in ranked]
        except Exception as e:  # noqa: BLE001
            print(f"[district_data] pure ML failed: {e}")
    return {
        "resolved_district": None, "resolved_state": None,
        "soil_used": None, "season": None,
        "top": results[0]["crop"] if results else None,
        "results": results,
        "note": "district not recognised - pure ML ranking",
    }
