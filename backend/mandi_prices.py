"""
Mandi price service for FarmIntel (Phase 1 — real data only).

Lookup order (all REAL, no synthetic layer anywhere):
  1. LIVE    - api.data.gov.in AGMARKNET resource for the requested
               district (self-healing probe with a hard timeout).
  2. LOCAL   - the local price store (mandi_prices), the district's own
               quotes for its most recent trading day, reported as the
               median of those mandis instead of one arbitrary row.
  3. MONTHLY - the district's own published AGMARKNET monthly average. This
               is preferred over another district's daily quote: a Kolar
               farmer is better served by Kolar's October average for rice
               than by one Thirthahalli mandi's price 300 km away.
  4. STATE   - live (then cached) rows for the same state only.
  5. INDIA   - nationwide rows, but ONLY for an unscoped request (no district
               and no state). A scoped request never borrows another state's
               market: an Odisha rate shown on a Jharkhand page is a lie even
               when the row itself is real.
  6. MSP     - government reference price, clearly labelled (never passed
               off as a mandi observation).
  7. NONE    - {source: unavailable}; the frontend renders "Unavailable".

Every response also carries `scope` (district | state | india | msp) so the
UI can say how far the search had to widen.

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

from crop_names import resolve_native
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


_STORED_NAMES = {"t": 0.0, "names": {}}


def stored_commodity(name: str) -> Optional[str]:
    """The spelling the price store actually uses for this commodity.

    AGMARKNET names carry qualifiers — "Ragi(Finger Millet)",
    "Arecanut(Betelnut/Supari)". Reducing those to a bare word ("Ragi")
    silently misses every row and lands on the MSP reference instead, so an
    exact stored spelling is always preferred over an alias.
    """
    key = _norm(name)
    if not key:
        return None
    return _stored_names().get(key)


def _stored_names() -> dict:
    """{normalised name: stored spelling}, refreshed every 10 minutes."""
    now = time.time()
    if now - _STORED_NAMES["t"] > 600 or not _STORED_NAMES["names"]:
        try:
            names = {_norm(n): n for n in price_store.distinct_commodities()}
            _STORED_NAMES.update(t=now, names=names)
        except Exception:  # noqa: BLE001 - a price lookup must never raise
            pass
    return _STORED_NAMES["names"]


def clamp_to_store(name: str) -> Optional[str]:
    """The store spelling closest to `name`, or None when nothing fits.

    Order: exact (ignoring spacing), then a unique prefix. "Ragi" finds
    "Ragi(Finger Millet)" because exactly one stored name starts with it;
    "Bengal Gram" fits several, so nothing is returned rather than picking a
    crop the farmer did not ask for.
    """
    key = _norm(name)
    stored = _stored_names()
    if not key or not stored:
        return None
    squashed = key.replace(" ", "")
    exact = [real for norm_name, real in stored.items()
             if norm_name.replace(" ", "") == squashed]
    if exact:
        return exact[0]
    pref = [real for norm_name, real in stored.items()
            if norm_name.replace(" ", "").startswith(squashed)]
    return pref[0] if len(pref) == 1 else None


def resolve_commodity(name: str) -> Optional[str]:
    key = _norm(name)
    if not key:
        return None
    # An already-correct stored spelling ("Ragi(Finger Millet)") is passed
    # through untouched. Resolution itself stays canonical —
    # "ರಾಗಿ" -> "Ragi" — and get_price() widens a canonical name to the
    # spelling the store uses before querying it.
    exact = stored_commodity(name)
    if exact:
        return exact
    if key in _COMMODITY_ALIASES:
        return _COMMODITY_ALIASES[key]
    # Regional-script name ("ಟೊಮೆಟೊ", "टमाटर") -> English AGMARKNET commodity.
    native = resolve_native(key)
    if native:
        return native
    # "Arecanut(Betelnut/Supari)" -> "arecanut" -> look the alias up again so
    # the canonical AGMARKNET spelling (with brackets) is preserved.
    base = key.split("(")[0].strip()
    if base in _COMMODITY_ALIASES:
        return _COMMODITY_ALIASES[base]
    native = resolve_native(base)
    if native:
        return native
    # A word in a regional script that we cannot translate must not be turned
    # into a plausible-looking commodity: say we don't know instead.
    if base and not base.isascii():
        return None
    return base.title() if base else None


# ---------------------------------------------------------------------------
# Live AGMARKNET (api.data.gov.in) with self-healing probe
# ---------------------------------------------------------------------------

_LIVE_URL = ("https://api.data.gov.in/resource/"
             "9ef84268-d588-465a-a308-a864a43d0070")

# Reuse the shared .env loader so the server and ingest jobs both see
# DATA_GOV_API_KEY from Farm_intel/.env without a dotenv dependency.
from config import settings

try:
    import mandi_ingest  # noqa: F401  (imports price_store; no cycle)
    mandi_ingest.load_env()
except ImportError:
    pass

_LIVE_KEY = settings.data_gov_api_key
# The feed normally answers in well under a second, but api.data.gov.in
# regularly pauses for several seconds under load. Five seconds marked a
# healthy feed dead and served days-old cache instead; twelve leaves room for
# a slow answer while still bounding a page render.
_LIVE_TIMEOUT = 12.0
# One failed probe used to silence the live feed for ten minutes, so every
# market page fell back to a cache that could be days old even though the API
# was healthy again a second later. Retry quickly; report the failure in
# /market/status instead of hiding live data behind it.
_RETRY_AFTER_FAILURE = 30

_live_state = {"alive": None, "last_probe": 0.0}
_live_lock = threading.Lock()

# Resolved spellings for districts, keyed by the name the app asked for. A
# district's stored spelling does not change, so one lookup per name is enough.
_DISTRICT_SPELLING: Dict[str, str] = {}

_DISTRICT_API_ALIASES = {
    # The app ships current official spellings; AGMARKNET (and the price
    # store built from it) still uses the older ones. Without these, picking
    # "Davanagere" in the district menu asked the feed for a district that
    # does not exist under that spelling and the page fell back to the
    # state's crops with no mandis at all.
    "davanagere": "Davangere",
    "chikkaballapura": "Chikballapur",
    "chikkamagaluru": "Chikmagalur",
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
                now - _live_state["last_probe"] < _RETRY_AFTER_FAILURE:
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


# The app ships current official state names; AGMARKNET (and therefore the
# price store) still uses these spellings.
_STATE_API_ALIASES = {
    "kerala": "Keralam",
    "chhattisgarh": "Chattisgarh",
    "delhi": "NCT of Delhi",
    "andaman and nicobar islands": "Andaman and Nicobar",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli",
}


def _district_name(district: Optional[str]) -> Optional[str]:
    """Official/UI district name -> the spelling AGMARKNET and the store use.

    A static alias covers the known renames; when the store already holds rows
    for the district it is the authority on how they are spelled, so a name
    the alias table has never heard of (a new district, a state-specific
    spelling) still lands on its real crops and mandis instead of nothing.
    """
    if not district:
        return None
    name = str(district).strip()
    aliased = _DISTRICT_API_ALIASES.get(_norm(name), name)
    cached = _DISTRICT_SPELLING.get(_norm(name))
    if cached:
        return cached
    try:
        stored = price_store.resolve_district(aliased) or price_store.resolve_district(name)
    except Exception:  # noqa: BLE001 - naming a district must never raise
        stored = None
    if stored:
        _DISTRICT_SPELLING[_norm(name)] = stored
        return stored
    return aliased


def _district_aliases(district: Optional[str]) -> List[str]:
    """Every stored spelling this district might appear under."""
    if not district:
        return []
    out = {v for k, v in _DISTRICT_API_ALIASES.items()
           if _norm(district) in (k, _norm(v)) and _norm(v) != _norm(district)}
    # The store's own spelling table knows the rest (Davanagere/Davangere).
    try:
        out |= price_store.name_variants(district)
        stored = _district_name(district)
        if stored:
            out.add(stored)
    except Exception:  # noqa: BLE001
        pass
    out.discard(str(district).strip())
    return sorted(o for o in out if o and _norm(o) != _norm(district))


def _state_name(state: Optional[str]) -> Optional[str]:
    if not state:
        return None
    name = str(state).strip()
    return _STATE_API_ALIASES.get(_norm(name), name)


def _state_aliases(state: Optional[str]) -> List[str]:
    """Every stored spelling this state might appear under."""
    if not state:
        return []
    return [v for k, v in _STATE_API_ALIASES.items()
            if _norm(state) in (k, _norm(v)) and _norm(v) != _norm(state)]


# A district page asks for the whole district at once; even a busy mandi
# district files a few hundred rows on one trading day, so one page covers it
# and no crop or mandi is cut off by the limit.
_LIVE_DISTRICT_LIMIT = 1000
_DISTRICT_FEED_TTL = 90        # seconds a successful district snapshot is reused
_DISTRICT_FEED_FAIL_TTL = 15   # retry a failed fetch quickly
# Even an explicit refresh waits this long after a failed attempt, so an
# outage cannot turn every page view into a 12-second stall.
_DISTRICT_FEED_MIN_RETRY = 8
_DISTRICT_FEED: Dict[tuple, dict] = {}
_DISTRICT_FEED_LOCK = threading.Lock()


def district_live_snapshot(district: str, state: Optional[str] = None,
                           force: bool = False) -> dict:
    """Everything the live AGMARKNET feed has for one district right now.

    Prices were read one commodity at a time, so a district page mixed today's
    quote for one crop with the store's cached copy for the rest — and any crop
    missing from the cache showed nothing at all although the live feed had it.
    One call per district keeps every card on the same trading day, discovers
    the mandis (and the crops) the cache has never seen, and writes the rows to
    the store so the latest prices survive an API outage.

    Cached for `_DISTRICT_FEED_TTL` seconds: the feed updates once a day, and a
    page rendering twenty cards must not fire twenty identical requests. When
    the feed cannot be reached the last snapshot we did get is served (flagged
    `live: False`), because the district's own crops and mandis are still the
    truthful answer — an empty snapshot is what used to make the page fall
    back to the whole state.
    """
    if not district:
        return {"live": False, "records": 0, "markets": [], "commodities": []}
    # Ask and answer under the spelling the feed/store actually hold
    # (Davanagere -> Davangere), or every row below misses.
    canonical = _district_name(district) or district
    key = (_norm(canonical), _norm(state))
    now = time.time()
    with _DISTRICT_FEED_LOCK:
        hit = _DISTRICT_FEED.get(key)
        if hit:
            ttl = _DISTRICT_FEED_TTL if hit["data"].get("live") else _DISTRICT_FEED_FAIL_TTL
            if now - hit["t"] < ttl and not force:
                return hit["data"]
            # An explicit refresh still honours a short backoff after a failed
            # attempt, so an outage cannot stall every page view.
            if force and not hit["data"].get("live") and \
                    now - hit["t"] < _DISTRICT_FEED_MIN_RETRY:
                return hit["data"]

    # The feed's district filter is loose (it also ignores a misspelled
    # district and can answer with a neighbouring one), so every row is
    # checked against the district that was asked for.
    allowed = {_norm(canonical), _norm(district)}
    allowed |= {_norm(a) for a in _district_aliases(canonical)}
    rows: List[dict] = []
    for rec in _live_records("", canonical, limit=_LIVE_DISTRICT_LIMIT,
                            state=state):
        if _norm(rec.get("district")) not in allowed:
            continue
        commodity = (rec.get("commodity") or "").strip()
        if not commodity:
            continue
        packed = _pack(commodity, rec.get("district") or canonical,
                       rec.get("market") or "",
                       rec.get("modal_price"), rec.get("min_price"),
                       rec.get("max_price"),
                       _fmt_live_date(rec.get("arrival_date")),
                       "agmarknet_live", state=rec.get("state"), scope="district",
                       requested_district=district)
        if not packed:
            continue
        rows.append({
            "date": packed["date"], "state": rec.get("state") or "",
            "district": packed["district"] or "", "market": packed["market"],
            "commodity": commodity, "variety": rec.get("variety") or "",
            "min_price": packed["min_price"], "max_price": packed["max_price"],
            "modal_price": packed["price"], "source": "agmarknet_live",
        })
    if rows:
        try:
            price_store.upsert_many(rows)
            # The feed is the authority for the district's latest trading day.
            # Anything else stored under `agmarknet_live` for that day came
            # from the loose commodity filter and carries another crop's price.
            keep = {(r["market"].strip(), r["commodity"].strip(),
                     (r["variety"] or "").strip()) for r in rows}
            latest = max(r["date"] for r in rows)
            price_store.prune_live_rows((rows[0].get("state") or ""), canonical,
                                       latest, keep)
        except Exception:  # noqa: BLE001 - serving prices must not raise
            pass

    if not rows:
        # No live answer (outage, or a district that filed nothing today).
        # Keep the crops and mandis we already know for this district instead
        # of returning an empty snapshot that widens the page to the state.
        with _DISTRICT_FEED_LOCK:
            prev = _DISTRICT_FEED.get(key)
            data = {**(prev["data"] if prev else {
                "records": 0, "markets": [], "commodities": [],
                "latest_date": None}),
                "live": False,
                "cached": bool(prev),
                "cached_at": prev["t"] if prev else None}
            _DISTRICT_FEED[key] = {"t": now, "data": data}
            return data

    data = {
        "live": True,
        "cached": False,
        "records": len(rows),
        "latest_date": max((r["date"] for r in rows), default=None),
        "commodities": sorted({r["commodity"] for r in rows}),
        "markets": sorted({r["market"] for r in rows if r["market"]}),
    }
    with _DISTRICT_FEED_LOCK:
        _DISTRICT_FEED[key] = {"t": now, "data": data}
    return data


def _same_commodity(rec_commodity, *wanted: str) -> bool:
    """Does a live row actually describe the crop that was asked for?

    api.data.gov.in treats the commodity filter loosely: asking for
    "Bajra(Pearl Millet/Cumbu)" in Davangere returns the district's Ragi row
    (the bracket seems to truncate the filter). Without this guard the Bajra
    card showed Ragi's ₹3,657 — a real price for the wrong crop.
    """
    got = _norm(rec_commodity)
    if not got:
        return False
    return any(got == _norm(w) for w in wanted if w)


def _live_records(commodity: str, district: Optional[str],
                  limit: int = 3, state: Optional[str] = None) -> List[dict]:
    params: Dict[str, object] = {"limit": limit}
    if commodity:
        params["filters[commodity]"] = commodity
    if district:
        params["filters[district]"] = _district_name(district)
    if state:
        params["filters[state]"] = _state_name(state)
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
    # A published monthly average is real but coarse — it must never wear the
    # same "Live" badge as a transaction filed today.
    if "monthly" in src:
        return "monthly"
    if src.startswith(_REAL_SOURCES_PREFIX):
        return "live" if date_str == today else "cached"
    return "unavailable"


def _days_old(date_str: str) -> Optional[int]:
    """How many days before today this quote was published.

    A mandi does not trade that crop every day, so "not today" is normal. The
    UI needs the age to say "latest available, 3 days old" instead of hiding a
    perfectly good price because it is not from today.
    """
    try:
        d = pd.to_datetime(str(date_str))
    except Exception:  # noqa: BLE001
        return None
    return max(0, (pd.Timestamp(date.today()) - d.normalize()).days)


def _pack(commodity: str, district: Optional[str], market: str,
          modal, mn, mx, date_str: str, source: str,
          state: Optional[str] = None,
          scope: str = "district",
          requested_district: Optional[str] = None) -> dict:
    try:
        modal = float(modal)
    except (TypeError, ValueError):
        modal = None
    if not modal or modal <= 0:
        return {}
    age = _days_old(date_str)
    return {
        "commodity": commodity,
        "district": district,
        # The district the farmer asked about, kept separate from the district
        # the row came from so a widened result can be labelled honestly
        # instead of looking like a quote from their own mandi.
        "requested_district": requested_district,
        "source_district": district,
        "state": state,
        "market": market or "",
        "price": round(modal, 2),
        "min_price": round(float(mn), 2) if mn else None,
        "max_price": round(float(mx), 2) if mx else None,
        "date": date_str,
        "days_old": age,
        "is_today": bool(age == 0),
        "unit": "₹/quintal",
        "source": source,
        "badge": _badge_from(source, date_str),
        "is_real": True,
        # how wide the search had to go to find this row: district | state |
        # india. The UI labels the card with it so a state-level rate is never
        # mistaken for a mandi in the farmer's own district.
        "scope": scope,
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
        "state": None,
        "market": "MSP reference (Govt of India 2024-25)",
        "unit_hint": "government reference price, not a mandi trade",
        "price": float(msp),
        "min_price": None,
        "max_price": None,
        "date": "2024-25",
        "days_old": None,
        "is_today": False,
        "unit": "₹/quintal",
        "source": "msp_reference",
        "badge": "msp",
        "scope": "msp",
        "requested_district": district,
        "source_district": None,
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
# One quote per district-day
# ---------------------------------------------------------------------------

# A daily quote older than this is not better than the district's published
# monthly average, which covers every mandi in the district rather than one.
_DAILY_WINDOW_DAYS = 45
# How old a published monthly average may be while it still outranks a
# different district's daily quote (two months of slack for slow reporting).
_MONTHLY_WINDOW_DAYS = 75


def _median(values: List[float]) -> Optional[float]:
    vals = sorted(float(v) for v in values if v)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def _district_quote(store_name: str, district: str) -> dict:
    """Representative price for a district's most recent trading day.

    Mandis in one district can file the same crop on the same day at prices
    that differ by a factor of two (Rice on 2026-10-29: ₹2,500 at one Karnataka
    mandi, ₹8,971 at another). `ORDER BY date DESC LIMIT 1` made the headline
    number depend on which row the database happened to return first, so a
    Kolar farmer could be shown a single distant mandi's outlier as "the"
    price. Taking the median of the district's own quotes for its latest day
    keeps the headline number representative; the cheapest and dearest quotes
    of that day stay in the min/max range.
    """
    try:
        rows = price_store.lookup(
            store_name, district, None, max_age_days=_DAILY_WINDOW_DAYS,
            limit=400, allow_any=False,
            district_aliases=_district_aliases(district))
    except Exception:  # noqa: BLE001 - a price lookup must never raise
        return {}
    if not rows:
        return {}
    day = max(r["date"] for r in rows)
    same = [r for r in rows if r["date"] == day]
    prices = [float(r["modal_price"]) for r in same if r["modal_price"]]
    median = _median(prices)
    if not median:
        return {}
    mins = [float(r["min_price"]) for r in same if r["min_price"]]
    maxs = [float(r["max_price"]) for r in same if r["max_price"]]
    markets = sorted({(r["market"] or "").strip() for r in same if r["market"]})
    if len(markets) == 1:
        label = markets[0]
    elif markets:
        label = f"median of {len(markets)} mandis in {district}"
    else:
        label = f"{district} average"
    return {
        "date": day,
        "price": median,
        "min_price": min(mins) if mins else min(prices),
        "max_price": max(maxs) if maxs else max(prices),
        "market": label,
        "source": same[0]["source"],
        "state": same[0]["state"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_price(commodity: str, district: Optional[str] = None,
              state: Optional[str] = None,
              allow_live: bool = True,
              strict_district: bool = False) -> Optional[dict]:
    """Best real price for a crop in a scope.

    `allow_live=False` skips the AGMARKNET live probe and answers from the
    local store only. Callers that must stay fast and deterministic (the crop
    advisor scoring five candidates at once) use it: a live outage there would
    otherwise change which crop gets recommended.

    `strict_district=True` never widens past the requested district: the
    Market page lists one district's crops and mandis, so a rate from a
    neighbouring district would misrepresent what that mandi paid. When the
    district has nothing the answer is None ("unavailable"), not a borrowed
    quote.
    """
    resolved = resolve_commodity(commodity)
    if not resolved:
        return None
    # The store may carry a qualified spelling ("Ragi(Finger Millet)" for a
    # bare "Ragi"); use it for every local query so those rows are found.
    store_name = clamp_to_store(resolved) or resolved

    district = str(district).strip() if district else None
    state = str(state).strip() if state else None
    wants_district = bool(district and _norm(district) not in ("", "all", "none"))
    wants_state = bool(state and _norm(state) not in ("", "all", "none"))
    scoped = wants_district or wants_state
    # A district alone still implies a state when the store knows one, so the
    # search widens at most one step (district -> its state) instead of
    # landing on whatever market happens to be newest anywhere in India.
    if wants_district and not wants_state:
        stored_state = price_store.state_for_district(_district_name(district))
        if stored_state:
            state, wants_state = stored_state, True

    # A strict district page pulls the district's whole live feed once; asking
    # the feed again per commodity would burn the API quota for the same rows.
    # The snapshot also persists them, so a later outage still serves today's
    # prices from the store.
    if strict_district and wants_district and allow_live:
        if district_live_snapshot(district, state if wants_state else None).get("live"):
            allow_live = False

    # 1. live AGMARKNET for the requested district. A state-scoped request
    #    keeps the state filter: without it the feed answers with whatever
    #    mandi is newest anywhere in the country.
    for rec in (_live_records(resolved, district,
                              state=state if wants_state else None)
                if allow_live else []):
        # The feed's commodity filter is loose; never price crop A with crop
        # B's row.
        if not _same_commodity(rec.get("commodity"), resolved, store_name):
            continue
        # Compare on every spelling the district goes by: the feed answers
        # "Davangere" for a page that asked for "Davanagere".
        district_keys = {_norm(district)} | {_norm(a) for a in _district_aliases(district)}
        same_district = bool(wants_district) and _norm(rec.get("district")) in district_keys
        if strict_district and wants_district and not same_district:
            continue
        packed = _pack(store_name, rec.get("district") or district,
                       rec.get("market") or "",
                       rec.get("modal_price"), rec.get("min_price"),
                       rec.get("max_price"),
                       _fmt_live_date(rec.get("arrival_date")),
                       "agmarknet_live",
                       state=rec.get("state"),
                       scope=("district" if same_district
                              else ("state" if scoped else "india")),
                       requested_district=district)
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

    # 2. cached REAL history (the backfill + accumulated daily fetches) for
    #    the requested district, aggregated to one quote per trading day.
    #    A scoped request never falls through to another state's market here.
    if wants_district:
        hit = _district_quote(store_name, district)
        if hit:
            packed = _pack(store_name, district, hit["market"],
                           hit["price"], hit["min_price"], hit["max_price"],
                           hit["date"], f"cache_{hit['source']}",
                           state=hit["state"] or state, scope="district",
                           requested_district=district)
            if packed:
                return packed

    # 3. the district's own published monthly average (AGMARKNET district
    #    monthly analysis). Preferred over another district's daily quote:
    #    Kolar's October rice average describes Kolar, while a Thirthahalli
    #    quote describes Thirthahalli. A month-average is coarser, so the
    #    source name and "monthly" badge say exactly what it is, and a stale
    #    month is skipped so a fresh state quote still wins.
    if wants_district:
        monthly = _monthly_pack(store_name, district, state,
                                scope_state=state,
                                max_age_days=_MONTHLY_WINDOW_DAYS, widen=False)
        if monthly:
            return monthly

    # A strict district request stops here: the last real trade in *this*
    # district, however old, and otherwise an honest "unavailable".
    if strict_district and wants_district:
        for row in price_store.lookup(
                store_name, district, None, max_age_days=730, allow_any=False,
                district_aliases=_district_aliases(district)):
            packed = _pack(store_name, district, row["market"],
                           row["modal_price"], row["min_price"],
                           row["max_price"], row["date"],
                           f"cache_stale_{row['source']}", state=row["state"],
                           scope="district", requested_district=district)
            if packed:
                packed["badge"] = "stale"
                age = packed.get("days_old")
                packed["detail"] = (
                    f"Latest real trade in {district}"
                    + (f" was {age} days ago" if age is not None else " is older than this season")
                    + " — shown with its date rather than as today's rate."
                )
                return packed
        # The district's own published monthly average, however old, is still
        # a Davangere number — dated and badged as a month average. Better
        # than "--" for a crop the district is listed as trading.
        monthly = _monthly_pack(store_name, district, state, scope_state=state,
                                max_age_days=None, widen=False)
        if monthly:
            return monthly
        return None

    # 4. live AGMARKNET for the same state, or anywhere only for an
    #    All-India request (which is what an unscoped lookup means).
    if allow_live and (not scoped or wants_state):
        for rec in _live_records(resolved, None,
                                 state=state if scoped else None):
            if not _same_commodity(rec.get("commodity"), resolved, store_name):
                continue
            packed = _pack(store_name, rec.get("district"), rec.get("market") or "",
                           rec.get("modal_price"), rec.get("min_price"),
                           rec.get("max_price"),
                           _fmt_live_date(rec.get("arrival_date")),
                           "agmarknet_live_other_market",
                           state=rec.get("state"),
                           scope="state" if scoped else "india",
                           requested_district=district)
            if packed:
                return packed

    # 5. cached daily rows for the state (or the whole country, only when the
    #    request itself was unscoped): the district reports nothing for this
    #    crop, so the nearest real rate in its own state is the honest answer.
    for row in price_store.lookup(
            store_name, None, state, allow_any=not scoped,
            district_aliases=_district_aliases(district),
            state_aliases=_state_aliases(state)):
        scope = "state" if scoped else "india"
        packed = _pack(store_name, row["district"] or district,
                       row["market"], row["modal_price"],
                       row["min_price"], row["max_price"],
                       row["date"], f"cache_{row['source']}",
                       state=row["state"], scope=scope,
                       requested_district=district)
        if packed:
            return packed

    # 6. published monthly average, widened from the district to its state.
    #    Without the widening a crop the state publishes monthly but the
    #    district does not (Coconut in Punjab, Turmeric in Kerala) was listed
    #    in the crop picker and then showed "--" for its price.
    monthly = _monthly_pack(store_name, district, state, scope_state=state,
                            widen=True)
    if monthly:
        return monthly

    # 7. last real trade, however old. A crop the catalogue lists but the
    #    45/120-day window skips would otherwise show "Unavailable" while a
    #    real mandi record sits in the store. The date and age are returned,
    #    so a 140-day-old rate is never mistaken for today's.
    for row in price_store.lookup(
            store_name, district, state, max_age_days=730,
            allow_any=not scoped,
            district_aliases=_district_aliases(district),
            state_aliases=_state_aliases(state)):
        same_district = wants_district and _norm(row["district"]) in {
            _norm(district), *(_norm(a) for a in _district_aliases(district))}
        packed = _pack(store_name, row["district"] or district,
                       row["market"], row["modal_price"],
                       row["min_price"], row["max_price"],
                       row["date"], f"cache_stale_{row['source']}",
                       state=row["state"],
                       scope="district" if same_district else ("state" if scoped else "india"),
                       requested_district=district)
        if packed:
            packed["badge"] = "stale"
            age = packed.get("days_old")
            packed["detail"] = (
                f"Latest real AGMARKNET trade for {store_name}"
                + (f" was {age} days ago" if age is not None else " is older than this season")
                + " — shown with its date rather than as today's rate."
            )
            return packed

    # 8. MSP reference — labelled, never passed off as a mandi price
    msp = _msp_pack(resolved, district)  # MSP table uses canonical names
    if msp:
        return msp

    return None


def _monthly_pack(commodity: str, district: Optional[str],
                  state: Optional[str], scope_state: Optional[str],
                  max_age_days: Optional[int] = None,
                  widen: bool = True) -> dict:
    """Latest published monthly average for the scope, if any.

    Returned as `agmarknet_monthly` with the month as its date, so the UI can
    label it "monthly average" instead of passing a month-average off as
    today's mandi rate.

    `widen=True` retries statewide when the district has no published rows of
    its own: the state average is still a real AGMARKNET figure, and leaving
    it out is how a crop ended up in the picker with no price. `max_age_days`
    lets a caller refuse an old month (the district-priority slot does), while
    the last-resort slot accepts any age because it is dated and badged.
    """
    scope = "district" if district else ("state" if state else "india")
    # Query under the store's spelling (Davanagere -> Davangere) while the
    # caller's name stays on the card.
    stored_district = _district_name(district) if district else None
    try:
        df = price_store.monthly_history(commodity, district=stored_district or district,
                                         state=state)
    except Exception:  # noqa: BLE001 - a price lookup must never raise
        return {}
    if (df is None or df.empty) and widen and district and state:
        try:
            df = price_store.monthly_history(commodity, district=None, state=state)
        except Exception:  # noqa: BLE001
            df = None
        if df is not None and not df.empty:
            district, scope = None, "state"
    if df is None or df.empty:
        return {}
    last = df.iloc[-1]
    # The average for the current month is published before the month ends; a
    # "date" in the future (30 Nov while it is 9 Nov) is not a quote that
    # exists, so cap it at today.
    month_end = min(pd.Timestamp(last["date"]) + pd.offsets.MonthEnd(0),
                    pd.Timestamp(date.today()))
    if max_age_days is not None:
        age = _days_old(month_end.strftime("%Y-%m-%d"))
        if age is not None and age > max_age_days:
            return {}
    return _pack(commodity, district, "monthly average",
                 last["price"], None, None,
                 month_end.strftime("%Y-%m-%d"), "agmarknet_monthly",
                 state=scope_state or state,
                 scope=scope,
                 requested_district=district)


def _fmt_live_date(s):
    try:
        return pd.to_datetime(str(s), format="%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        try:
            return pd.to_datetime(s).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return str(date.today() - timedelta(days=1))


def district_markets(district: Optional[str], state: Optional[str] = None,
                     refresh: bool = False) -> List[str]:
    """Every mandi that reports in this district — live feed first.

    The store only knew the mandis that had been ingested, so a district with
    a live feed full of mandis showed a handful of them. One district refresh
    discovers them all (and keeps them, because the rows are stored).
    """
    if not district:
        return []
    # One snapshot call (TTL-cached) is the live part of the answer; `refresh`
    # just bypasses that cache so the list is today's feed.
    snapshot = district_live_snapshot(district, state, force=refresh)
    names = {(m or "").strip() for m in (snapshot.get("markets") or [])}
    # Match the store on both spellings: the page asks for "Davanagere" while
    # the rows say "Davangere", and an exact comparison listed no mandis.
    allowed = {_norm(district), _norm(_district_name(district) or district)}
    allowed |= {_norm(a) for a in _district_aliases(district)}
    try:
        for m in price_store.distinct_markets():
            if _norm(m.get("district")) in allowed:
                names.add((m.get("market") or "").strip())
    except Exception:  # noqa: BLE001
        pass
    return sorted(n for n in names if n)


def scope_commodities(district: Optional[str] = None,
                      state: Optional[str] = None,
                      predictable: bool = False,
                      strict_district: bool = False,
                      refresh: bool = False) -> dict:
    """Commodities with a real row in this district/state.

    Widening stops at one step — district, then its state — because the
    Market page only offers "my district" and "my state". When the district
    has nothing, `scope` says "state" so the UI can name what it is showing.
    """
    district = str(district).strip() if district else None
    state = str(state).strip() if state else None
    wants_district = bool(district and _norm(district) not in ("", "all", "none"))
    wants_state = bool(state and _norm(state) not in ("", "all", "none"))
    if wants_district and not wants_state:
        stored = price_store.state_for_district(_district_name(district))
        if stored:
            state, wants_state = stored, True

    def _query(d: Optional[str], s: Optional[str]) -> List[str]:
        return price_store.distinct_commodities(
            d, s, allow_any=not (wants_district or wants_state),
            district_aliases=_district_aliases(d),
            state_aliases=_state_aliases(s))

    # A district page must describe one district. Its own crops are pulled
    # fresh from the live feed first (that is where a mandi the ingest never
    # saw shows up), then the store is read, and *only* those crops are listed.
    # The broad "district crops + the rest of the state" list is still what an
    # unscoped district listing means elsewhere, so it stays the default.
    live: dict = {}
    # A district page must describe one district. Its own crops are pulled
    # fresh from the live feed first (that is where a mandi the ingest never
    # saw shows up), then the store is read, and *only* those crops are listed.
    # The broad "district crops + the rest of the state" list stays the default
    # for unscoped callers.
    if wants_district and strict_district:
        # Refresh asks the feed again (the Refresh button); otherwise the
        # snapshot's own short TTL keeps it current without a request per card.
        live = district_live_snapshot(district, state if wants_state else None,
                                      force=refresh)
        local = sorted(set(_query(district, state)) | set(live.get("commodities") or []))
        commodities, scope = local, "district"
    else:
        # A district only trades some crops on some days, but the farmer still
        # wants to see what the rest of their state is paying for coconut or
        # ragi. So the list is the district's own crops first, then everything
        # else the state reports — each price call then says which it found.
        local = _query(district, state) if wants_district else []
        statewide = _query(None, state) if wants_state else []
        if wants_district:
            commodities = list(local) + [c for c in statewide if c not in local]
            scope = "district" if local else ("state" if statewide else "all")
        else:
            commodities = list(statewide) if wants_state else _query(None, None)
            scope = "state" if wants_state else "all"

    if predictable:
        # Only crops the model can actually run here: enough daily observations
        # or published monthly averages. District and state are both tried, and
        # the full scoped list is kept when nothing qualifies, so the picker is
        # never empty.
        usable = set(price_store.forecastable_commodities(
            state if wants_state else None,
            district if wants_district else None))
        if wants_state:
            usable |= set(price_store.forecastable_commodities(state, None))
        narrowed = [c for c in commodities if c in usable]
        if narrowed:
            commodities = narrowed
    out = {
        "commodities": commodities,
        "district_commodities": list(local),
        "scope": scope,
        "district": district,
        "state": state,
        "predictable": predictable,
    }
    if strict_district and wants_district:
        # The district page names the mandis it is actually summarising: every
        # one the live feed reported plus every one the store has filed for
        # the district, and nothing from a neighbouring district.
        out["live"] = bool(live.get("live"))
        out["cached"] = bool(live.get("cached"))
        out["latest_date"] = live.get("latest_date")
        out["markets"] = sorted(
            set(live.get("markets") or []) | set(district_markets(district, state)))
    return out


def status() -> dict:
    cov = price_store.coverage()
    return {
        "local_source": True,
        "coverage": cov,
        "live_endpoint": _live_state["alive"],
        "live_last_probe": _live_state["last_probe"],
        "ingest_configured": bool(_LIVE_KEY),
    }
