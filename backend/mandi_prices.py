"""
Mandi price service for FarmIntel (Phase 1 — real data only).

Lookup order (all REAL, no synthetic layer anywhere):
  1. LIVE   - api.data.gov.in AGMARKNET resource for the requested
              district (self-healing probe with a hard timeout).
  2. CACHE  - the local price store (mandi_prices table), which holds the
              accumulated history: the real Goa 2024-2026 backfill plus
              every daily live fetch since ingestion started.
  3. LIVE-anywhere - the live resource without a district filter.
  4. MSP    - government reference price, clearly labelled (never passed
              off as a mandi observation).
  5. NONE   - {source: unavailable}; the frontend renders "Unavailable".

The old synthetic snapshot (mandi_price_history.csv, hash-generated
district prices) has been REMOVED: silent invented prices were the bug
flagged in the Phase 0 audit. When nothing real is available the app
says "Unavailable" instead of showing a number of unknown provenance.

Every response carries: price, min/max, market name, date, source and a
`badge` of "live" | "cached" | "msp" | "unavailable".
"""

from __future__ import annotations

import os
import re
import time
import threading
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests

import price_store

# ---------------------------------------------------------------------------
# Commodity aliasing (frontend/recommendation names -> dataset names)
# ---------------------------------------------------------------------------

_COMMODITY_ALIASES = {
    "paddy": "Rice", "rice": "Rice", "maize": "Maize", "wheat": "Wheat",
    "cotton": "Cotton", "onion": "Onion", "tomato": "Tomato",
    "potato": "Potato", "banana": "Banana", "mango": "Mango",
    "papaya": "Papaya", "watermelon": "Watermelon", "water melon": "Watermelon",
    "muskmelon": "Muskmelon", "coconut": "Coconut", "orange": "Orange",
    "grapes": "Grapes", "apple": "Apple", "green chilli": "Green Chilli",
    "brinjal": "Brinjal", "pineapple": "Pineapple", "cashew": "Cashewnuts",
    "cashewnuts": "Cashewnuts", "arecanut": "Arecanut(Betelnut/Supari)",
    "copra": "Copra", "tur": "Arhar/Tur", "arhar": "Arhar/Tur",
    "moong": "Moong", "urad": "Urad", "gram": "Gram", "chickpea": "Gram",
    "groundnut": "Groundnut", "jowar": "Jowar", "bajra": "Bajra",
    "ragi": "Ragi", "sugarcane": "Sugarcane", "jute": "Jute",
    "coffee": "Coffee", "marigold": "Marigold(Loose)", "rose": "Rose(Loose)",
    "mousambi": "Mousambi(Sweet Lime)", "chikoos": "Chikoos(Sapota)",
    "sapota": "Chikoos(Sapota)", "barley": "Barley", "soybean": "Soybean",
    "mustard": "Mustard", "sunflower": "Sunflower", "sesamum": "Sesamum",
    "castor": "Castor", "lentil": "Lentil", "pomegranate": "Pomegranate",
    "turmeric": "Turmeric",
}

_REAL_SOURCES_PREFIX = ("agmarknet", "cache")   # all *real* sources start with one of these

# Government MSP 2024-25 reference prices, ₹/quintal
_MSP_2024_25 = {
    "paddy (common)": 2300, "paddy": 2300, "rice": 2300, "wheat": 2425,
    "barley": 1985, "maize": 2225, "jowar (sorghum)": 3371, "jowar": 3371,
    "bajra (pearl millet)": 2625, "bajra": 2625,
    "ragi (finger millet)": 4290, "ragi": 4290,
    "gram (chickpea)": 5650, "gram": 5650, "chickpea": 5650,
    "tur (pigeon pea)": 7550, "tur": 7550, "arhar/tur": 7550,
    "moong (green gram)": 8682, "moong": 8682, "mungbean": 8682,
    "urad (black gram)": 7400, "urad": 7400, "blackgram": 7400,
    "lentil (masoor)": 6425, "lentil": 6425, "groundnut": 6783,
    "soybean": 4892, "sunflower": 7280, "sesamum": 8346, "mustard": 5650,
    "cotton": 7121, "jute": 5685, "copra": 16500, "sugarcane": 340,
}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def resolve_commodity(name: str) -> Optional[str]:
    key = _norm(name)
    if not key:
        return None
    if key in _COMMODITY_ALIASES:
        return _COMMODITY_ALIASES[key]
    base = key.split("(")[0].strip()
    return base.title() if base else None


# ---------------------------------------------------------------------------
# Live AGMARKNET (api.data.gov.in) with self-healing probe
# ---------------------------------------------------------------------------

_LIVE_URL = ("https://api.data.gov.in/resource/"
             "9ef84268-d588-465a-a308-a864a43d0070")

# Reuse the shared .env loader so the server and ingest jobs both see
# DATA_GOV_API_KEY from Farm_intel/.env without a dotenv dependency.
try:
    import mandi_ingest  # noqa: F401  (imports price_store; no cycle)
    mandi_ingest.load_env()
except ImportError:
    pass

_LIVE_KEY = os.environ.get("DATA_GOV_API_KEY", "")
_LIVE_TIMEOUT = 5.0
_PROBE_EVERY = 600

_live_state = {"alive": None, "last_probe": 0.0}
_live_lock = threading.Lock()

_DISTRICT_API_ALIASES = {
    "belagavi": "Belgaum", "bengaluru urban": "Bangalore",
    "bengaluru rural": "Bangalore Rural", "ballari": "Bellary",
    "mysuru": "Mysore", "tumakuru": "Tumkur", "shivamogga": "Shimoga",
    "kalaburagi": "Gulbarga", "vijayapura": "Bijapur",
    "spsr nellore": "Nellore", "y s r": "Kadapa",
    "chhatrapati sambhajinagar": "Aurangabad",
    "dharashiv": "Osmanabad", "narmadapuram": "Hoshangabad",
    "ahilyanagar": "Ahmednagar", "prayagraj": "Allahabad",
    "sahibzada ajit singh nagar": "Mohali",
}


def _live_get(params: dict) -> Optional[dict]:
    now = time.time()
    with _live_lock:
        if _live_state["alive"] is False and \
                now - _live_state["last_probe"] < _PROBE_EVERY:
            return None
    try:
        r = requests.get(_LIVE_URL, params={**params, "api-key": _LIVE_KEY,
                                            "format": "json"},
                         headers={"User-Agent": "FarmIntel/3.0",
                                  "Accept": "application/json"},
                         timeout=_LIVE_TIMEOUT)
        with _live_lock:
            _live_state.update(alive=r.status_code == 200, last_probe=now)
        return r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        with _live_lock:
            _live_state.update(alive=False, last_probe=now)
        return None


def _live_records(commodity: str, district: Optional[str],
                  limit: int = 3) -> List[dict]:
    params: Dict[str, object] = {"limit": limit}
    if commodity:
        params["filters[commodity]"] = commodity
    if district:
        d = _DISTRICT_API_ALIASES.get(_norm(district), str(district).strip())
        params["filters[district]"] = d
    data = _live_get(params)
    if not data:
        return []
    return data.get("records") or []


# ---------------------------------------------------------------------------
# Packing + badges
# ---------------------------------------------------------------------------

def _badge_from(source: str, date_str: str) -> str:
    src = (source or "").lower()
    today = date.today().strftime("%Y-%m-%d")
    if "msp" in src:
        return "msp"
    if src.startswith(_REAL_SOURCES_PREFIX):
        return "live" if date_str == today else "cached"
    return "unavailable"


def _pack(commodity: str, district: Optional[str], market: str,
          modal, mn, mx, date_str: str, source: str) -> dict:
    try:
        modal = float(modal)
    except (TypeError, ValueError):
        modal = None
    if not modal or modal <= 0:
        return {}
    return {
        "commodity": commodity,
        "district": district,
        "market": market or "",
        "price": round(modal, 2),
        "min_price": round(float(mn), 2) if mn else None,
        "max_price": round(float(mx), 2) if mx else None,
        "date": date_str,
        "unit": "₹/quintal",
        "source": source,
        "badge": _badge_from(source, date_str),
        "is_real": True,
    }


# ---------------------------------------------------------------------------
# MSP reference (real government-announced price, clearly labelled)
# ---------------------------------------------------------------------------

def _msp_pack(commodity: str, district: Optional[str]) -> dict:
    msp = _msp_for(commodity)
    if not msp:
        return {}
    return {
        "commodity": commodity,
        "district": district,
        "market": "MSP reference (Govt of India 2024-25)",
        "price": float(msp),
        "min_price": None,
        "max_price": None,
        "date": "2024-25",
        "unit": "₹/quintal",
        "source": "msp_reference",
        "badge": "msp",
        # the MSP is a real government announcement — but not a market
        # transaction. Consumers must not treat it as observed mandi data.
        "is_real": False,
        "note": "Government Minimum Support Price — not a mandi observation",
    }


def _msp_for(commodity: str) -> Optional[float]:
    key = _norm(commodity)
    if key in _MSP_2024_25:
        return _MSP_2024_25[key]
    base = key.split("(")[0].strip()
    return _MSP_2024_25.get(base)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_price(commodity: str, district: Optional[str] = None,
              state: Optional[str] = None) -> Optional[dict]:
    resolved = resolve_commodity(commodity)
    if not resolved:
        return None

    # 1. live AGMARKNET for the requested district
    for rec in _live_records(resolved, district):
        packed = _pack(resolved, rec.get("district") or district,
                       rec.get("market") or "",
                       rec.get("modal_price"), rec.get("min_price"),
                       rec.get("max_price"),
                       _fmt_live_date(rec.get("arrival_date")),
                       "agmarknet_live")
        if packed:
            # also persists into the store for history/forecasting
            price_store.upsert_many([{
                "date": packed["date"], "state": rec.get("state") or "",
                "district": packed["district"] or "", "market": packed["market"],
                "commodity": resolved, "variety": rec.get("variety") or "",
                "min_price": packed["min_price"], "max_price": packed["max_price"],
                "modal_price": packed["price"], "source": "agmarknet_live",
            }])
            return packed

    # 2. cached REAL history (Goa backfill + accumulated daily fetches)
    for row in price_store.lookup(resolved, district, state):
        packed = _pack(resolved, row["district"] or district,
                       row["market"], row["modal_price"],
                       row["min_price"], row["max_price"],
                       row["date"], f"cache_{row['source']}")
        if packed:
            return packed

    # 3. live AGMARKNET for the commodity anywhere in India
    for rec in _live_records(resolved, None):
        packed = _pack(resolved, rec.get("district"), rec.get("market") or "",
                       rec.get("modal_price"), rec.get("min_price"),
                       rec.get("max_price"),
                       _fmt_live_date(rec.get("arrival_date")),
                       "agmarknet_live_other_market")
        if packed:
            return packed

    # 4. MSP reference — labelled, never passed off as a mandi price
    msp = _msp_pack(resolved, district)
    if msp:
        return msp

    return None


def _fmt_live_date(s):
    try:
        return pd.to_datetime(str(s), format="%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        try:
            return pd.to_datetime(s).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return str(date.today() - timedelta(days=1))


def status() -> dict:
    cov = price_store.coverage()
    return {
        "local_source": True,
        "coverage": cov,
        "live_endpoint": _live_state["alive"],
        "live_last_probe": _live_state["last_probe"],
        "ingest_configured": bool(_LIVE_KEY),
    }
