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
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))  # legacy checkout root


def _first_existing(*paths: str) -> str:
    """First path that exists, so the bundled dataset is found however the
    repo was checked out (backend/data, repo root, or the old layout)."""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


# Bundled with the repo (backend/data). The other locations keep working for
# checkouts that predate the move.
SOIL_CSV = _first_existing(
    os.path.join(BASE_DIR, "data", "soil_with_coordinates.csv"),
    os.path.join(os.path.dirname(BASE_DIR), "soil_with_coordinates.csv"),
    os.path.join(PROJECT_ROOT, "soil_with_coordinates.csv"),
)
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


def _band_shares(high, medium, low, names=("high", "medium", "low")) -> dict:
    """Sample counts -> share of samples in each band (fractions, sum to 1)."""
    zero = {n: 0.0 for n in names}
    vals = [high, medium, low]
    if any(v is None or (isinstance(v, float) and np.isnan(float(v))) for v in vals):
        return zero
    high, medium, low = float(high), float(medium), float(low)
    total = high + medium + low
    if total <= 0:
        return zero
    return {names[0]: round(high / total, 3),
            names[1]: round(medium / total, 3),
            names[2]: round(low / total, 3)}


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
    # Organic-carbon sample counts per district. The survey publishes three
    # bands rather than a figure, and the fertiliser model needs a number, so
    # the band shares are kept here to build an estimate (see organic_carbon).
    SOIL_OC: Dict[str, list] = {}
    # The survey's own low/medium/high sample counts per nutrient. The fertiliser
    # dose engine has to classify a district as low/medium/high the same way the
    # ICAR tables do, and the survey already publishes exactly that split - using
    # the smoothed kg/ha estimate for it would be a category error.
    SOIL_BANDS: Dict[str, dict] = {}
    for _, r in agg.iterrows():
        prof = _profile_from_row(r)
        SOIL_PROFILES[r["district"]] = prof
        SOIL_PROFILE_INDEX.setdefault(r["district"], []).append(prof)
        SOIL_OC[r["district"]] = [float(r.get("oc_high") or 0),
                                   float(r.get("oc_medium") or 0),
                                   float(r.get("oc_low") or 0)]
        SOIL_BANDS[r["district"]] = {
            "N": _band_shares(r.get("n_high"), r.get("n_medium"), r.get("n_low")),
            "P": _band_shares(r.get("p_high"), r.get("p_medium"), r.get("p_low")),
            "K": _band_shares(r.get("k_high"), r.get("k_medium"), r.get("k_low")),
            "pH": _band_shares(r.get("ph_acidic"), r.get("ph_neutral"),
                               r.get("ph_alkaline"),
                               names=("acidic", "neutral", "alkaline")),
        }
except Exception as e:  # noqa: BLE001
    print(f"[district_data] soil CSV load failed: {e}")
    SOIL_PROFILES = {}
    SOIL_PROFILE_INDEX = {}
    SOIL_OC = {}
    SOIL_BANDS = {}


# Organic-carbon band midpoints, as percentages of soil organic carbon. The
# survey reports how many samples fell in each band; these are the conventional
# midpoints for low (<0.5%), medium (0.5-0.75%) and high (>0.75%) carbon.
OC_BAND_MIDPOINTS = {"low": 0.35, "medium": 0.62, "high": 1.25}


def organic_carbon(district: Optional[str], state: Optional[str] = None,
                   lat: Optional[float] = None,
                   lon: Optional[float] = None) -> Optional[dict]:
    """Estimated soil organic carbon (%), from the district's OC band shares.

    The fertiliser model was trained with organic carbon as an input because
    it is what separates a compost recommendation from a balanced NPK one; the
    DES survey only publishes band counts, so the estimate is the weighted mean
    of the band midpoints. `band` reports which band dominates, so a caller can
    describe the input honestly instead of implying a laboratory figure.
    """
    loc = resolve_district(district, state, lat, lon)
    if not loc:
        return None
    counts = SOIL_OC.get(loc["district"])
    if not counts:
        return None
    high, medium, low = counts
    total = high + medium + low
    if total <= 0:
        return None
    value = (high * OC_BAND_MIDPOINTS["high"]
             + medium * OC_BAND_MIDPOINTS["medium"]
             + low * OC_BAND_MIDPOINTS["low"]) / total
    dominant = max((("high", high), ("medium", medium), ("low", low)),
                   key=lambda x: x[1])[0]
    return {
        "value": round(float(value), 3),
        "band": dominant,
        "source": "district_soil_survey",
        "shares": {"high": round(high / total, 3),
                   "medium": round(medium / total, 3),
                   "low": round(low / total, 3)},
    }


def nutrient_bands(district: Optional[str], state: Optional[str] = None,
                   lat: Optional[float] = None,
                   lon: Optional[float] = None) -> Optional[dict]:
    """District soil status as low/medium/high, straight from the survey.

    The DES district survey reports how many samples fell in each of the three
    fertility bands for N, P and K, and the same split for soil reaction. The
    dominant band is therefore the district's status, which is the same
    classification the ICAR tables use - no threshold is applied to a smoothed
    estimate that was never a soil test value.
    """
    loc = resolve_district(district, state, lat, lon)
    if not loc:
        return None
    bands = SOIL_BANDS.get(loc["district"])
    if not bands:
        return None
    levels = {}
    for nut in ("N", "P", "K"):
        shares = bands.get(nut) or {}
        if not shares or not any(shares.values()):
            continue
        levels[nut] = max(shares, key=shares.get)
    ph_shares = bands.get("pH") or {}
    if any(ph_shares.values()):
        levels["pH"] = max(ph_shares, key=ph_shares.get)
    return {
        "district": loc.get("district"),
        "state": loc.get("state"),
        "levels": levels,
        "shares": bands,
        "source": "district_soil_survey",
    }


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

# District-trained suitability model (see train_crop_model.py). It scores
# (district soil + climate + crop identity) -> probability the district grows
# that crop in that season, trained on the shipped district table. Absent on a
# checkout that has not run the trainer; the seven-feature model above then
# remains the ML signal.
try:
    _bundle = joblib.load(os.path.join(MODELS_DIR, "crop_model.pkl"))
    CROP_MODEL = _bundle if (isinstance(_bundle, dict)
                             and _bundle.get("task") == "crop_suitability"
                             and _bundle.get("model") is not None) else None
except Exception as e:  # noqa: BLE001
    print(f"[district_data] district crop model load failed: {e}")
    CROP_MODEL = None


def crop_model_info() -> Optional[dict]:
    """Which ML signal /predict is using, and its measured accuracy.

    Exposed through /model/status so the report's numbers are checkable from a
    running server rather than only from the trainer's stdout.
    """
    if not CROP_MODEL:
        return None
    g = (CROP_MODEL.get("metrics") or {}).get(
        CROP_MODEL.get("model_name"), {}).get("grouped_by_district", {})
    return {
        "model": CROP_MODEL.get("model_name"),
        "trained_at": CROP_MODEL.get("trained_at"),
        "crops": CROP_MODEL.get("crops"),
        "districts": len(CROP_MODEL.get("districts") or {}),
        "examples": CROP_MODEL.get("examples"),
        "grouped_precision_at_3": g.get("precision_at_3"),
        "grouped_recall_at_3": g.get("recall_at_3"),
        "grouped_auc": g.get("auc"),
        "baselines": CROP_MODEL.get("baselines"),
    }


def _suitability_inputs(loc: Optional[dict], season: str,
                        temperature: float, humidity: float,
                        rainfall: float) -> Optional[np.ndarray]:
    """The district half of the suitability model's feature vector.

    The trained table stores one soil/coordinate block per district (every
    column is constant within a district), so a known district is looked up
    and an unknown one falls back to its nearest known district - the same
    ~120 km guard `resolve_district` uses for coordinates. Live weather wins
    over the district's climatology, so a hot week moves the score.
    """
    if not CROP_MODEL or not loc:
        return None
    districts = CROP_MODEL.get("districts") or {}
    if not districts:
        return None

    key = _alias(loc.get("district") or "") if loc.get("district") else ""
    block = districts.get(key)
    if block is None and loc.get("lat") is not None and loc.get("lon") is not None:
        best, best_d = None, float("inf")
        for name, cand in districts.items():
            dd = ((cand["latitude"] - loc["lat"]) ** 2
                  + (cand["longitude"] - loc["lon"]) ** 2)
            if dd < best_d:
                best, best_d = cand, dd
        if best is not None and best_d < 1.5:
            block = best
    if block is None and loc.get("state"):
        # No district match and no usable coordinates (the state-merge path):
        # average the state's districts so the score still reflects the right
        # soil and climate band instead of dropping to the climate-only model.
        peers = [v for v in districts.values()
                 if v.get("state") == _norm(loc["state"])]
        if peers:
            block = {k: float(np.mean([p[k] for p in peers]))
                     for k in ("n_index", "p_index", "k_index", "ph_index",
                               "oc_high", "oc_medium", "oc_low",
                               "ec_nonsaline", "ec_saline",
                               "latitude", "longitude")}
            block["climate"] = {}
    if block is None:
        return None

    season_key = "rabi" if _norm(season) == "rabi" else "kharif"
    clim = (block.get("climate") or {}).get(season_key) or {}
    dist_block = {
        "n_index": block["n_index"], "p_index": block["p_index"],
        "k_index": block["k_index"], "ph_index": block["ph_index"],
        "oc_high": block["oc_high"], "oc_medium": block["oc_medium"],
        "oc_low": block["oc_low"], "ec_nonsaline": block["ec_nonsaline"],
        "ec_saline": block["ec_saline"],
        "latitude": loc.get("lat") if loc.get("lat") is not None
        else block["latitude"],
        "longitude": loc.get("lon") if loc.get("lon") is not None
        else block["longitude"],
        "temp": temperature if temperature is not None
        else clim.get("temp", 27.0),
        "humidity": humidity if humidity is not None
        else clim.get("humidity", 70.0),
        "rainfall": rainfall if rainfall is not None
        else clim.get("rainfall", 5.0),
        "season_rabi": 1.0 if season_key == "rabi" else 0.0,
    }
    return np.array([dist_block[f] for f in CROP_MODEL["district_features"]],
                    dtype=float)


def _suitability_probs(loc: Optional[dict], season: str,
                       temperature: float, humidity: float,
                       rainfall: float,
                       crop_names: List[str]) -> Dict[str, float]:
    """P(this district grows this crop in this season) for each candidate."""
    base = _suitability_inputs(loc, season, temperature, humidity, rainfall)
    if base is None or not crop_names:
        return {}
    vocab = CROP_MODEL["crops"]
    index = {c: i for i, c in enumerate(vocab)}
    rows, names = [], []
    for name in crop_names:
        i = index.get(_norm(name))
        if i is None:
            continue
        oh = np.zeros(len(vocab), dtype=float)
        oh[i] = 1.0
        rows.append(np.concatenate([base, oh]))
        names.append(_norm(name))
    if not rows:
        return {}
    try:
        proba = CROP_MODEL["model"].predict_proba(np.vstack(rows))[:, 1]
    except Exception as e:  # noqa: BLE001
        print(f"[district_data] suitability predict failed: {e}")
        return {}
    return {n: float(p) for n, p in zip(names, proba)}

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


def _season_fit(prof: Optional[dict], season: str) -> float:
    """0..1 fit of the crop's own sowing window to the asked-for season.

    "All" crops (tomato) and perennials (sugarcane) grow across seasons, so
    they are not penalised. A genuine mismatch (wheat asked for in kharif) is
    demoted rather than banned: a farmer may still want the number.
    """
    if not prof:
        return 0.5
    crop_season = _norm(prof.get("season") or "")
    asked = _norm(season or "kharif")
    if not crop_season:
        return 0.6
    if crop_season in ("all", "perennial", "annual", "whole year"):
        return 0.9
    parts = [p.strip() for p in crop_season.replace("&", "/").split("/") if p.strip()]
    if asked in parts:
        return 1.0
    return 0.45


def _climate_fit(temperature: float, rainfall: float, prof: dict) -> float:
    """0..1 fit of the live climate to a crop's temperature/rainfall window.

    Separate from `_soil_fit` (which covers NPK and pH) so the result can show
    "this soil suits it" and "this climate suits it" as two different facts.
    """
    if not prof:
        return 0.5
    t_min, t_max = prof.get("temp_min"), prof.get("temp_max")
    if t_min is None or t_max is None:
        t_fit = 0.5
    elif t_min <= temperature <= t_max:
        t_fit = 1.0
    else:
        dist = min(abs(temperature - t_min), abs(temperature - t_max))
        t_fit = max(0.0, 1.0 - dist / 12.0)

    # The live figure is a current-month value; annualising keeps the
    # comparison against an annual rainfall band meaningful.
    season_rain = float(rainfall) * 12.0
    r_min, r_max = prof.get("rain_min"), prof.get("rain_max")
    if not r_min or not r_max:
        rain_fit = 0.5
    elif season_rain <= r_min:
        rain_fit = max(0.2, 1.0 - (r_min - season_rain) / r_min)
    elif season_rain >= r_max:
        rain_fit = max(0.2, 1.0 - (season_rain - r_max) / r_max)
    else:
        rain_fit = 1.0
    return float(np.clip(0.65 * t_fit + 0.35 * rain_fit, 0.0, 1.0))


# Crops whose yield band is measured on the raw crop while AGMARKNET stores
# the processed commodity under the same word.
_MARGIN_PRICE_COMMODITY = {"rice": "Paddy(Common)"}


def _crop_economics(candidates: List[Tuple[str, float]],
                    district: Optional[str],
                    state: Optional[str]) -> Dict[str, dict]:
    """Real mandi price x published yield band for each candidate crop.

    This is what turns a suitability ranking into a "which crop pays best"
    ranking: gross return per hectare = yield (t/ha) x 10 x modal price
    (Rs/quintal). It is revenue before input costs, and the API labels it that
    way - we have no cost-of-cultivation figures, so calling it profit would
    be a number we cannot defend.

    Prices are read from the local store and the published monthly averages
    only (`allow_live=False`): a recommendation must not wait on the live
    AGMARKNET feed, and an outage must not change which crop is recommended.
    """
    if not candidates:
        return {}
    try:
        import crop_info
        import mandi_prices
    except Exception:  # noqa: BLE001
        return {}

    names = [c for c, _p in candidates]
    yields: Dict[str, dict] = {}
    try:
        yields = crop_info.get_crop_info([n.title() for n in names])
    except Exception:  # noqa: BLE001
        yields = {}

    out: Dict[str, dict] = {}
    for crop_name in names:
        price = source = date_ = scope = badge = market = None
        # The published yield bands are of the harvested raw crop: rice's
        # 3.5-4.5 t/ha is paddy, so valuing it at the milled "Rice" rate
        # (~₹5,000/q) doubled its return against every other crop. The rate a
        # paddy grower is actually paid is the Paddy(Common) quote.
        price_commodity = _MARGIN_PRICE_COMMODITY.get(crop_name, crop_name)
        try:
            packed = mandi_prices.get_price(price_commodity, district, state,
                                            allow_live=False)
        except Exception:  # noqa: BLE001
            packed = None
        if packed and packed.get("price"):
            price = float(packed["price"])
            source = packed.get("source")
            date_ = packed.get("date")
            scope = packed.get("scope")
            badge = packed.get("badge")
            market = packed.get("market")
            src_district = packed.get("source_district") or packed.get("district")
        else:
            src_district = None

        info = yields.get(crop_name.title()) or {}
        band = info.get("yield_t_ha")
        gross = None
        if price and band and len(band) == 2 and band[1] > 0:
            mid = (float(band[0]) + float(band[1])) / 2.0 if band[0] > 0 else float(band[1])
            gross = round(mid * 10.0 * price, 2)

        # The one input cost this platform can actually price: the fertiliser
        # dose from the ICAR tables, at the manual's own 2021 rates. Seed,
        # labour and machinery are not in it, so the result is a margin after
        # fertiliser - never presented as profit.
        cost = margin = None
        try:
            import fertilizer_dose
            levels = {}
            bands = nutrient_bands(district, state) if district else None
            for nut in ("N", "P", "K"):
                level = ((bands or {}).get("levels") or {}).get(nut)
                if level:
                    levels[nut] = level
            dose = fertilizer_dose.compute_dose(
                crop_name.title(), None, None, None, None,
                levels=levels or None,
                levels_source="district_soil_survey" if levels else "default_medium")
            estimate = fertilizer_dose.estimate_cost(dose) \
                if dose.get("available") else None
            if estimate:
                cost = estimate["fertiliser_cost_per_ha"]
                if gross:
                    margin = round(float(gross) - cost, 2)
        except Exception as e:  # noqa: BLE001 - economics must not break ranking
            print(f"[district_data] fertiliser cost failed for {crop_name}: {e}")

        out[crop_name] = {
            "fertiliser_cost_per_ha": cost,
            "margin_after_fertiliser_per_ha": margin,
            "cost_basis": ("ICAR FertiSolver Appendix-B, 2021 prices; fertiliser "
                           "only, excludes seed/labour/machinery")
            if cost is not None else None,
            "market_price": price,
            "price_commodity": price_commodity,
            "market_price_source": source,
            "market_price_date": date_,
            "market_price_scope": scope,
            "market_price_badge": badge,
            "market": market,
            "price_district": src_district,
            "yield_t_ha": list(band) if band else None,
            "gross_return_per_ha": gross,
        }
    return out


def _score_candidates(
    N: float, P: float, K: float, ph: float,
    temperature: float, humidity: float, rainfall: float,
    candidates: List[Tuple[str, float]],
    hist: Dict[str, dict],
    loc: dict,
    season: str,
    top_n: int,
    state_fallback: bool = False,
    economics: Optional[Dict[str, dict]] = None,
) -> dict:
    """Rank candidate crops with ML probability, historical yield/area,
    soil fit, climate fit and what the crop actually earns per hectare -
    shared by the district path and the state-merge path."""
    master = MASTER_CROPS
    # The district survey values, reported back as `soil_used`; the scoring
    # itself uses the caller's N/P/K/ph, which are these values unless the
    # farmer sent their own soil test.
    district_soil = loc.get("soil")

    ml_probs: Dict[str, float] = {}
    if ML_MODEL is not None and ML_LE is not None:
        try:
            feats = np.array([[N, P, K, temperature, humidity, ph, rainfall]])
            probas = ML_MODEL.predict_proba(feats)[0]
            ml_probs = dict(zip(ML_LE.classes_, probas))
        except Exception as e:  # noqa: BLE001
            print(f"[district_data] ML predict failed: {e}")

    # District-trained suitability score, when the bundle is present. This is
    # the ML signal the ranking prefers: it is conditioned on this district's
    # soil survey and climate band, not just on the season's weather.
    suit_probs = _suitability_probs(
        loc, season, temperature, humidity, rainfall,
        [c for c, _p in candidates])

    econ = economics or {}
    gross_values = [e["gross_return_per_ha"] for e in econ.values()
                    if e.get("gross_return_per_ha")]
    max_gross = max(gross_values) if gross_values else 0.0
    price_values = [e["market_price"] for e in econ.values()
                    if e.get("market_price")]
    max_price = max(price_values) if price_values else 0.0

    results = []
    for crop_name, prior in candidates:
        ml_label = _ml_label(crop_name)
        p_climate = float(ml_probs.get(ml_label, 0.0)) if ml_label else 0.0
        local = suit_probs.get(_norm(crop_name))
        if local is not None:
            p_ml, ml_source = float(local), "district"
        else:
            p_ml, ml_source = p_climate, ("climate" if ml_label else "none")
        h = hist.get(crop_name, {})
        yield_s = float(h.get("yield_score", 0) or 0)
        area_s = float(h.get("area_share", 0) or 0)
        hist_score = (0.55 * yield_s + 0.45 * area_s) * prior

        prof = master.get(crop_name)
        if prof:
            # Score the soil this answer is actually based on: the farmer's own
            # soil test when one was sent, the district survey otherwise. This
            # used to always read the district survey, so a typed soil test
            # moved the ML feature vector but never the "soil match" the page
            # showed - the same soil-fit number appeared for every soil test.
            soil_fit = _soil_fit(N, P, K, ph, prof, rainfall)
        else:
            soil_fit = 0.5
        climate_fit = _climate_fit(temperature, rainfall, prof) if prof else 0.5
        season_fit = _season_fit(prof, season)

        e = econ.get(crop_name) or {}
        gross = e.get("gross_return_per_ha")
        if gross and max_gross > 0:
            market_score = float(gross) / max_gross
        elif e.get("market_price") and max_price > 0:
            # No yield band for this crop, so its price alone is only a weak
            # signal - cap it well below a crop with a measured return.
            market_score = 0.4 * float(e["market_price"]) / max_price
        else:
            market_score = 0.0

        # A crop that holds a sliver of the district's cropped area is not
        # "the best crop for this soil" even when its price is high: rice in
        # Kolar covers ~1% of the area while ragi covers ~18%, and the price
        # term alone was enough to put rice first. Suitability still scales
        # the score, but locality gates how far a rare crop can climb.
        locality = 0.55 + 0.45 * min(1.0, float(area_s) / _LOCAL_AREA_SHARE) \
            if not state_fallback else 1.0

        if state_fallback:
            # No district history backs these candidates, so lean on the
            # curated prior, agronomic fit and what the crop earns here
            # instead of letting a single strong ML class dominate.
            raw = (0.22 * p_ml + 0.15 * hist_score + 0.14 * soil_fit
                   + 0.08 * climate_fit + 0.05 * season_fit + 0.11 * prior
                   + 0.25 * market_score)
        else:
            raw = (0.20 * p_ml + 0.18 * hist_score + 0.14 * area_s
                   + 0.14 * soil_fit + 0.09 * climate_fit + 0.05 * season_fit
                   + 0.05 * prior + 0.15 * market_score)
        final = raw * locality
        results.append({
            "crop": CATEGORY_DISPLAY.get(crop_name, crop_name.title()),
            "raw_crop": crop_name,
            "ml_label": ml_label,
            "ml_prob": round(p_ml, 4),
            "ml_source": ml_source,
            "hist_score": round(float(hist_score), 3),
            "soil_fit": round(float(soil_fit), 3),
            "climate_fit": round(float(climate_fit), 3),
            "season_fit": round(float(season_fit), 3),
            "region_share": round(float(area_s), 4),
            "locality": round(float(locality), 3),
            "market_score": round(float(market_score), 3),
            "market_price": e.get("market_price"),
            "price_commodity": e.get("price_commodity"),
            "market_price_source": e.get("market_price_source"),
            "market_price_date": e.get("market_price_date"),
            "market_price_scope": e.get("market_price_scope"),
            "market_price_badge": e.get("market_price_badge"),
            "price_market": e.get("market"),
            "price_district": e.get("price_district"),
            "yield_t_ha": e.get("yield_t_ha"),
            "gross_return_per_ha": gross,
            "fertiliser_cost_per_ha": e.get("fertiliser_cost_per_ha"),
            "margin_after_fertiliser_per_ha":
                e.get("margin_after_fertiliser_per_ha"),
            "cost_basis": e.get("cost_basis"),
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
            if prof:
                sf = _soil_fit(N, P, K, ph, prof, rainfall)
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

    # Confidence rescale so the top crop shows a believable % match. Scaled
    # proportionally: the old clamp put every near-tie at 97%, which read like
    # a bug when two crops showed the identical score.
    top = float(results[0]["final_score"]) if results else 0.0
    display_scores = []
    for r in results:
        ratio = (float(r["final_score"]) / top) if top > 0 else 0.0
        display_scores.append(round(min(0.97, 0.35 + 0.62 * ratio), 4))

    return {
        "resolved_district": loc.get("district"),
        "resolved_state": loc.get("state"),
        "soil_used": district_soil,
        "season": season,
        "top": results[0]["crop"] if results else None,
        "economics": {
            "prices_used": bool(gross_values),
            "basis": ("yield band (t/ha) × latest real mandi price (₹/quintal), "
                      "before input costs"),
        },
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
                    state_fallback=True,
                    economics=_crop_economics(
                        state_cands, district or loc_for_score["district"],
                        state or st))
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
        candidates, hist, loc, season, top_n,
        economics=_crop_economics(candidates, district or d, state or loc.get("state")))


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


# Share of a district's cropped area at which a crop counts as locally
# established. Below it the locality gate scales the score down, so a crop the
# district barely grows cannot top the list on price alone.
_LOCAL_AREA_SHARE = 0.15


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
