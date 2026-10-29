"""
Real crop agronomy info (Phase 2).

Sources (both local, no per-request fabrication):
  1. FarmIntel_crop_master_v3_FIXED.xlsx - bundled agronomy dataset
     (family, season, soil type, pH range, temperature range, rainfall range).
  2. A reference table of days-to-maturity and average national yields for
     the 22 crops the RandomForest recommendation model can output, from
     standard published Indian agronomy figures (ICAR/MoAFW state averages,
     2023-24). Perennial crops carry `period_note` instead of a single
     duration value.

Crops the model does not know simply omit those fields - the frontend
renders "--" instead of inventing numbers.
"""
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

BASE_DIR = Path(__file__).parent  # backend/
_MASTER_CANDIDATES = [
    BASE_DIR / "FarmIntel_crop_master_v3_FIXED.xlsx",
    BASE_DIR / "FarmIntel_crop_master_v3.xlsx",
    BASE_DIR.parent / "FarmIntel_crop_master_v3_FIXED.xlsx",
    BASE_DIR.parent / "FarmIntel_crop_master_v3.xlsx",
]

# RF model label -> crop master "crop" column (normalize() uses this list
# directly, so entries are both model labels and canonical master names)
ALIASES: Dict[str, str] = {
    "rice": "rice",
    "maize": "maize",
    "chickpea": "chickpea",
    "kidneybeans": "kidney bean",
    "pigeonpeas": "pigeon pea",
    "mothbeans": "moth bean",
    "mungbean": "green gram",
    "blackgram": "black gram",
    "lentil": "lentil",
    "pomegranate": "pomegranate",
    "banana": "banana",
    "mango": "mango",
    "grapes": "grapes",
    "watermelon": "watermelon",
    "muskmelon": "muskmelon",
    "apple": "apple",
    "orange": "orange",
    "papaya": "papaya",
    "coconut": "coconut",
    "cotton": "cotton",
    "jute": "jute",
    "coffee": "coffee",
}

# Standard published Indian agronomy figures. duration_days is the normal
# field days-to-maturity window; yield_t_ha is the national average band.
REFERENCE: Dict[str, dict] = {
    "rice":       {"duration": [120, 150], "yield": [3.5, 4.5], "water": "High"},
    "maize":      {"duration": [95, 110],  "yield": [2.5, 3.0], "water": "Medium"},
    "chickpea":   {"duration": [95, 110],  "yield": [0.9, 1.2], "water": "Low"},
    "kidney bean":{"duration": [90, 120],  "yield": [0.8, 1.0], "water": "Medium"},
    "pigeon pea": {"duration": [150, 180], "yield": [0.8, 1.1], "water": "Low"},
    "moth bean":  {"duration": [60, 75],   "yield": [0.4, 0.6], "water": "Low"},
    "green gram": {"duration": [65, 75],   "yield": [0.7, 1.0], "water": "Medium"},
    "black gram": {"duration": [75, 90],   "yield": [0.6, 0.8], "water": "Medium"},
    "lentil":     {"duration": [110, 125], "yield": [0.9, 1.1], "water": "Low"},
    "pomegranate":{"duration": [730, 910], "yield": [15, 25],   "water": "Medium",
                   "perennial": True},
    "banana":     {"duration": [330, 365], "yield": [25, 40],   "water": "High"},
    "mango":      {"duration": [0, 0],     "yield": [4, 10],    "water": "Medium",
                   "perennial": True,
                   "note": "First harvest 3-5 years after planting"},
    "grapes":     {"duration": [150, 175], "yield": [20, 30],   "water": "Medium",
                   "perennial": True},
    "watermelon": {"duration": [80, 100],  "yield": [25, 30],   "water": "High"},
    "muskmelon":  {"duration": [75, 90],   "yield": [15, 22],   "water": "High"},
    "apple":      {"duration": [150, 180], "yield": [10, 18],   "water": "Medium",
                   "perennial": True},
    "orange":     {"duration": [240, 270], "yield": [10, 15],   "water": "High",
                   "perennial": True},
    "papaya":     {"duration": [300, 360], "yield": [30, 45],   "water": "High"},
    "coconut":    {"duration": [0, 0],     "yield": [6, 10],    "water": "High",
                   "perennial": True,
                   "note": "First harvest 4-5 years after planting; bearing palms yield 5-7 years"},
    "cotton":     {"duration": [160, 185], "yield": [0.5, 0.7], "water": "Medium"},
    "jute":       {"duration": [110, 120], "yield": [1.6, 2.1], "water": "High"},
    "coffee":     {"duration": [0, 0],     "yield": [0.8, 1.3], "water": "Medium",
                   "perennial": True,
                   "note": "First harvest 3-4 years after planting"},
}

REF_SOURCE = "ICAR / MoAFW standard agronomy references (national averages)"
MASTER_SOURCE = "FarmIntel crop master dataset (bundled)"

_master_cache: Optional[pd.DataFrame] = None


def load_master() -> pd.DataFrame:
    """Cached, lower-cased crop master table. Empty frame if not bundled."""
    global _master_cache
    if _master_cache is not None:
        return _master_cache
    df = pd.DataFrame()
    for path in _MASTER_CANDIDATES:
        if path.exists():
            try:
                df = pd.read_excel(path)
                break
            except Exception:  # noqa: BLE001 - fall through to next candidate
                continue
    _master_cache = df
    return df


def normalize(name: str) -> str:
    """Accept any casing/canonical label ('PigeonPeas', 'mungbean', ...)."""
    key = (name or "").strip().lower().replace(" ", "")
    if key in ALIASES:
        return ALIASES[key]
    compact = {(k or "").replace(" ", ""): k for k in ALIASES}
    if key in compact:
        return ALIASES[compact[key]]
    # master-column names like "pigeon pea" compact to the same shape
    return key.replace(" ", "") if not key else key


def get_crop_info(raw_names: List[str]) -> Dict[str, dict]:
    """Per requested crop: real agronomy from the master dataset + reference
    table. Missing entries include an explicit `unavailable: True` so the
    caller never shows fabricated defaults."""
    master = load_master()
    master_idx: Dict[str, pd.Series] = {}
    if master is not None and not master.empty and "crop" in master.columns:
        for _, r in master.iterrows():
            name = str(r["crop"]).strip().lower()
            if name:
                master_idx.setdefault(name, r)

    out: Dict[str, dict] = {}
    for raw in raw_names:
        if not raw or not str(raw).strip():
            continue
        canon = normalize(raw)
        info: dict = {
            "requested": raw,
            "canonical": canon,
            "sources": {"master": MASTER_SOURCE, "reference": REF_SOURCE},
        }

        row = master_idx.get(canon)
        found_master = row is not None
        if found_master:
            info.update({
                "family": _clean(row.get("family")),
                "season": _clean(row.get("season")),
                "soil_type": _clean(row.get("soil_type")),
                "ph_range": _range(row.get("ph_min"), row.get("ph_max")),
                "temp_range_c": _range(row.get("temp_min"), row.get("temp_max"),
                                       suffix="°C"),
                "rainfall_range_mm": _range(row.get("rainfall_min"),
                                            row.get("rainfall_max"),
                                            suffix=" mm"),
                "ideal_npk": {
                    "N": _num(row.get("N")), "P": _num(row.get("P")),
                    "K": _num(row.get("K")),
                },
            })

        ref = REFERENCE.get(canon)
        if ref:
            # [0, 0] marks unknown maturity (perennial with notes) - make it
            # explicit null for the frontend instead of a meaningless pair.
            duration = ref["duration"]
            if tuple(duration) == (0, 0):
                duration = None
            info.update({
                "duration_days": duration,
                "yield_t_ha": ref["yield"],
                "water_needs": ref["water"],
                "perennial": ref.get("perennial", False),
                "maturity_note": ref.get("note"),
            })
        else:
            info.setdefault("duration_days", None)
            info.setdefault("yield_t_ha", None)
            info.setdefault("water_needs", None)
            if not found_master:
                info["unavailable"] = True  # neither source has this crop
        out[str(raw)] = info
    return out


def _clean(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _num(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _range(lo, hi, suffix: str = "") -> Optional[str]:
    lo_n, hi_n = _num(lo), _num(hi)
    if lo_n is None or hi_n is None:
        return None
    fmt = (lambda x: int(x) if float(x).is_integer() else round(x, 1))
    return f"{fmt(lo_n)} - {fmt(hi_n)}{suffix}"


def period_text(info: dict) -> str:
    """Human string for the dashboard 'period' chip, or None when unknown."""
    dur = info.get("duration_days")
    if not dur:
        return None
    if info.get("perennial") and info.get("maturity_note"):
        return None
    lo, hi = dur
    if not lo or not hi:
        return None
    if lo > 360:
        return "Perennial"
    months = [round(lo / 30.4), round(hi / 30.4)]
    if months[0] == months[1]:
        return f"{months[0]} Months"
    return f"{months[0]}-{months[1]} Months"
