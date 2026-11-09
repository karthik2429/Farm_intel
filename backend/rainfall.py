"""
Monthly rainfall per district, from the Open-Meteo historical archive.

Why this exists: most districts in the store have AGMARKNET *monthly average*
prices only, so the price model has no daily shape to learn from. Rain is the
one supply driver we can get as a genuine monthly history for every district
without an API key — the archive returns daily precipitation back to 1940, and
we total it per month and cache it next to the price store.

Nothing here invents data: a failed or partial fetch returns what was actually
returned, and the caller treats a missing district as "rain unknown" rather
than assuming a normal year.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

CACHE_PATH = Path(__file__).resolve().parent / "data" / "rainfall_cache.json"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
CACHE_TTL_S = 7 * 24 * 3600      # rainfall history does not change
_lock = threading.Lock()
_mem: Dict[str, dict] = {}


def _key(lat: float, lon: float) -> str:
    return f"{round(float(lat), 2)},{round(float(lon), 2)}"


def _load() -> dict:
    if _mem:
        return _mem
    try:
        with CACHE_PATH.open() as fh:
            _mem.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return _mem


def _save(data: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        with tmp.open("w") as fh:
            json.dump(data, fh)
        tmp.replace(CACHE_PATH)
    except OSError:
        pass


def monthly_rainfall(lat: Optional[float], lon: Optional[float],
                     start_year: int, end_year: int) -> Dict[str, float]:
    """{"YYYY-MM": mm} totals for the range, or {} when unavailable.

    One archive request covers the whole range; the result is cached on disk
    forever (historical rainfall is immutable) and in memory per process.
    """
    if lat is None or lon is None:
        return {}
    key = _key(lat, lon)
    data = _load()
    entry = data.get(key) or {}
    if entry.get("years", [0, 0])[0] <= start_year and \
            entry.get("years", [0, 0])[1] >= end_year and entry.get("months"):
        return entry["months"]
    if entry and time.time() - float(entry.get("t", 0)) < CACHE_TTL_S \
            and entry.get("months"):
        # Recent range already fetched and still fresh enough.
        covered = {int(m[:4]) for m in entry["months"]}
        if start_year in covered and end_year in covered:
            return entry["months"]

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": f"{start_year}-01-01",
        "end_date": f"{end_year}-12-31",
        "daily": "precipitation_sum",
        "timezone": "Asia/Kolkata",
    }
    try:
        resp = requests.get(ARCHIVE, params=params, timeout=20)
        daily = resp.json().get("daily") or {}
        times = daily.get("time") or []
        rain = daily.get("precipitation_sum") or []
    except Exception:  # noqa: BLE001 - rain is optional context, never fatal
        return entry.get("months") or {}

    months: Dict[str, float] = {}
    for day, mm in zip(times, rain):
        if day is None or mm is None:
            continue
        months[day[:7]] = months.get(day[:7], 0.0) + float(mm)
    if not months:
        return entry.get("months") or {}

    with _lock:
        data[key] = {"years": [start_year, end_year], "months": months,
                     "t": time.time()}
        _save(data)
    return months


def month_to_date(lat: Optional[float], lon: Optional[float],
                  today=None) -> Optional[float]:
    """Rainfall for the current calendar month, including the forecast ahead.

    The historical archive lags a few days, which would make a dry early month
    look dry right up to its cutoff. Open-Meteo's forecast endpoint carries
    `past_days`, so this combines what already fell with what is still coming
    for the same month.
    """
    if lat is None or lon is None:
        return None
    import datetime as _dt
    now = today or _dt.date.today()
    key = f"mtd:{_key(lat, lon)}:{now:%Y-%m}"
    data = _load()
    hit = data.get(key)
    if hit and time.time() - float(hit.get("t", 0)) < 1800:
        return hit.get("mm")

    params = {
        "latitude": lat, "longitude": lon,
        "daily": "precipitation_sum",
        "past_days": 31, "forecast_days": 16,
        "timezone": "Asia/Kolkata",
    }
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast",
                            params=params, timeout=12)
        daily = resp.json().get("daily") or {}
        times = daily.get("time") or []
        vals = daily.get("precipitation_sum") or []
    except Exception:  # noqa: BLE001
        return hit.get("mm") if hit else None

    total = 0.0
    seen = False
    for day, mm in zip(times, vals):
        if day is None or mm is None or day[:7] != f"{now:%Y-%m}":
            continue
        total += float(mm)
        seen = True
    if not seen:
        return hit.get("mm") if hit else None

    with _lock:
        data[key] = {"mm": round(total, 1), "t": time.time()}
        _save(data)
    return round(total, 1)


def month_normal(months: Dict[str, float], month: int,
                 exclude_year: Optional[int] = None) -> Tuple[Optional[float], int]:
    """Average rainfall for this calendar month across the years we have.

    Returns (normal_mm, years_used). `exclude_year` keeps the current year out
    of its own baseline, which would otherwise hide the anomaly we are trying
    to measure.
    """
    vals = [v for k, v in months.items()
            if int(k[5:7]) == month and (exclude_year is None or int(k[:4]) != exclude_year)]
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)
