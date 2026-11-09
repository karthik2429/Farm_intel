"""
Price context factors.

Holt-Winters forecasts a price from its own observed history. That model cannot
know that Diwali is six days away, that 120 mm of rain is forecast, or that half
the markets in a district stopped reporting. This module computes those drivers
from real inputs and returns them as *explanations around* the forecast — never
as invented numbers folded into it.

Every signal carries its own evidence and source, so the UI can show why it
appeared. When an input is unavailable (no coordinates, no history) the signal
is omitted rather than guessed.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

import price_store

# --------------------------------------------------------------------------- #
# Festivals
# --------------------------------------------------------------------------- #
# Demand-side calendar. Fixed-date festivals are exact; lunar ones vary by a day
# or two by region and are flagged `approx` so the UI can say so honestly.
FESTIVALS: List[Dict[str, Any]] = [
    # Past years are kept so the forecast can *measure* the festival effect on
    # stored prices instead of assuming one. upcoming_festivals() ignores them.
    # 2024
    {"name": "Makar Sankranti / Pongal", "date": "2024-01-15", "approx": True, "region": "national"},
    {"name": "Holi", "date": "2024-03-25", "approx": True, "region": "north"},
    {"name": "Eid al-Fitr", "date": "2024-04-10", "approx": True, "region": "national"},
    {"name": "Baisakhi", "date": "2024-04-13", "approx": False, "region": "north"},
    {"name": "Eid al-Adha", "date": "2024-06-17", "approx": True, "region": "national"},
    {"name": "Raksha Bandhan", "date": "2024-08-19", "approx": True, "region": "north"},
    {"name": "Janmashtami", "date": "2024-08-26", "approx": True, "region": "national"},
    {"name": "Ganesh Chaturthi", "date": "2024-09-07", "approx": True, "region": "west-south"},
    {"name": "Onam (Thiruvonam)", "date": "2024-09-15", "approx": True, "region": "kerala"},
    {"name": "Navratri", "date": "2024-10-03", "approx": True, "region": "west"},
    {"name": "Dussehra", "date": "2024-10-12", "approx": True, "region": "national"},
    {"name": "Diwali", "date": "2024-10-31", "approx": True, "region": "national"},
    {"name": "Chhath Puja", "date": "2024-11-07", "approx": True, "region": "east"},
    {"name": "Guru Nanak Jayanti", "date": "2024-11-15", "approx": True, "region": "north"},
    {"name": "Christmas", "date": "2024-12-25", "approx": False, "region": "national"},
    # 2025
    {"name": "Makar Sankranti / Pongal", "date": "2025-01-14", "approx": False, "region": "national"},
    {"name": "Republic Day", "date": "2025-01-26", "approx": False, "region": "national"},
    {"name": "Holi", "date": "2025-03-14", "approx": True, "region": "north"},
    {"name": "Ugadi / Gudi Padwa", "date": "2025-03-30", "approx": True, "region": "south-west"},
    {"name": "Eid al-Fitr", "date": "2025-03-31", "approx": True, "region": "national"},
    {"name": "Baisakhi", "date": "2025-04-14", "approx": False, "region": "north"},
    {"name": "Eid al-Adha", "date": "2025-06-07", "approx": True, "region": "national"},
    {"name": "Raksha Bandhan", "date": "2025-08-09", "approx": True, "region": "north"},
    {"name": "Janmashtami", "date": "2025-08-16", "approx": True, "region": "national"},
    {"name": "Ganesh Chaturthi", "date": "2025-08-27", "approx": True, "region": "west-south"},
    {"name": "Onam (Thiruvonam)", "date": "2025-09-05", "approx": True, "region": "kerala"},
    {"name": "Navratri", "date": "2025-09-22", "approx": True, "region": "west"},
    {"name": "Dussehra", "date": "2025-10-02", "approx": True, "region": "national"},
    {"name": "Diwali", "date": "2025-10-20", "approx": True, "region": "national"},
    {"name": "Chhath Puja", "date": "2025-10-28", "approx": True, "region": "east"},
    {"name": "Guru Nanak Jayanti", "date": "2025-11-05", "approx": True, "region": "north"},
    {"name": "Christmas", "date": "2025-12-25", "approx": False, "region": "national"},
    # 2026
    {"name": "Makar Sankranti / Pongal", "date": "2026-01-14", "approx": False, "region": "national"},
    {"name": "Republic Day", "date": "2026-01-26", "approx": False, "region": "national"},
    {"name": "Holi", "date": "2026-03-04", "approx": True, "region": "north"},
    {"name": "Ugadi / Gudi Padwa", "date": "2026-03-19", "approx": True, "region": "south-west"},
    {"name": "Eid al-Fitr", "date": "2026-03-20", "approx": True, "region": "national"},
    {"name": "Baisakhi", "date": "2026-04-14", "approx": False, "region": "north"},
    {"name": "Eid al-Adha", "date": "2026-05-27", "approx": True, "region": "national"},
    {"name": "Raksha Bandhan", "date": "2026-08-28", "approx": True, "region": "north"},
    {"name": "Onam (Thiruvonam)", "date": "2026-08-26", "approx": True, "region": "kerala"},
    {"name": "Janmashtami", "date": "2026-09-04", "approx": True, "region": "national"},
    {"name": "Ganesh Chaturthi", "date": "2026-09-14", "approx": True, "region": "west-south"},
    {"name": "Navratri", "date": "2026-10-11", "approx": True, "region": "west"},
    {"name": "Dussehra", "date": "2026-10-20", "approx": True, "region": "national"},
    {"name": "Diwali", "date": "2026-11-08", "approx": True, "region": "national"},
    {"name": "Chhath Puja", "date": "2026-11-15", "approx": True, "region": "east"},
    {"name": "Guru Nanak Jayanti", "date": "2026-11-24", "approx": True, "region": "north"},
    {"name": "Christmas", "date": "2026-12-25", "approx": False, "region": "national"},
    # 2027
    {"name": "Makar Sankranti / Pongal", "date": "2027-01-14", "approx": False, "region": "national"},
    {"name": "Republic Day", "date": "2027-01-26", "approx": False, "region": "national"},
    {"name": "Holi", "date": "2027-03-22", "approx": True, "region": "north"},
    {"name": "Baisakhi", "date": "2027-04-14", "approx": False, "region": "north"},
    {"name": "Diwali", "date": "2027-10-29", "approx": True, "region": "national"},
    {"name": "Christmas", "date": "2027-12-25", "approx": False, "region": "national"},
]

# Which Indian cropping season a date falls in — fixed solar windows, not guessed.
SEASONS = [
    ("Kharif harvest", 10, 1, 11, 30, "Kharif arrivals peak; prices usually soften."),
    ("Rabi sowing", 11, 1, 12, 31, "Sowing demand for inputs; stored stock released."),
    ("Rabi harvest", 3, 1, 4, 30, "Rabi arrivals peak; prices usually soften."),
    ("Zaid / summer", 5, 1, 6, 30, "Lean arrivals; prices usually firm up."),
]


def _in_window(d: date_cls, start_m: int, start_d: int, end_m: int, end_d: int) -> bool:
    """True when `d` falls in a (month, day) window, handling year wrap."""
    v = (d.month, d.day)
    start, end = (start_m, start_d), (end_m, end_d)
    if start <= end:
        return start <= v <= end
    return v >= start or v <= end


def current_season(on: Optional[date_cls] = None) -> Dict[str, Any]:
    """The agronomic season window `on` falls into (real calendar windows)."""
    d = on or date_cls.today()
    for name, sm, sd, em, ed, note in SEASONS:
        if _in_window(d, sm, sd, em, ed):
            return {"name": name, "note": note,
                    "window": f"{sm:02d}-{sd:02d} to {em:02d}-{ed:02d}"}
    return {"name": "Inter-season", "note": "Between major harvest windows.",
            "window": None}


def upcoming_festivals(days_ahead: int = 21,
                       on: Optional[date_cls] = None) -> List[Dict[str, Any]]:
    """Festivals inside the forecast horizon, sorted by how soon they are."""
    today = on or date_cls.today()
    horizon = today + timedelta(days=days_ahead)
    out = []
    for f in FESTIVALS:
        try:
            fd = datetime.strptime(f["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= fd <= horizon:
            out.append({**f, "days_until": (fd - today).days})
    return sorted(out, key=lambda x: x["days_until"])


# --------------------------------------------------------------------------- #
# Seasonality from real history
# --------------------------------------------------------------------------- #

def _scoped_history(commodity: str, district: Optional[str],
                    state: Optional[str], years: float, min_rows: int = 1):
    """
    Widest-enough scope, tried as district -> state -> national.

    A district that quoted the commodity once has *data* but not a usable
    sample, so scopes are skipped until one carries at least `min_rows` priced
    observations. Returns (df, scope) so the caller can label the answer
    honestly, and falls back to the largest sample seen if nothing qualifies.
    """
    attempts = []
    if district:
        attempts.append((district, state, "district"))
    if state:
        attempts.append((None, state, "state"))
    attempts.append((None, None, "national"))

    best = (None, None)
    best_n = 0
    for d, s, scope in attempts:
        df = price_store.history(commodity, district=d, state=s, years=years)
        if df is None or df.empty:
            continue
        n = int((df["modal_price"] > 0).sum())
        if n > best_n:
            best, best_n = (df, scope), n
        if n >= min_rows:
            return df, scope
    return best


def _feed_overlap(a: pd.Series, b: pd.Series) -> float:
    """How much of two samples came from the same feeds (1.0 = identical mix)."""
    wa = a.value_counts(normalize=True)
    wb = b.value_counts(normalize=True)
    keys = set(wa.index) | set(wb.index)
    return float(sum(min(wa.get(k, 0.0), wb.get(k, 0.0)) for k in keys))


def seasonality(commodity: str, district: Optional[str] = None,
                state: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Compare this calendar month's historical average with the commodity's own
    overall average, using only stored observations. Returns None when there is
    not enough history to say anything.
    """
    df, scope = _scoped_history(commodity, district, state, years=3.0,
                                min_rows=40)
    if df is None or "modal_price" not in df.columns:
        return None

    df = df[df["modal_price"] > 0].copy()
    if df.empty:
        return None

    # Compare a window around today's day-of-year (not just the calendar month)
    # so a thin month still has enough observations to say something real.
    today = pd.Timestamp(date_cls.today())
    window = 15
    df["year"] = df["date"].dt.year
    doy = df["date"].dt.dayofyear
    target = today.dayofyear
    # circular distance in day-of-year, so December windows wrap into January
    diff = (doy - target).abs()
    near_mask = (diff <= window) | (diff >= 365 - window)
    near = df[near_mask]
    if len(near) < 15:
        return None

    # A seasonal *index*, not a raw price gap: each year's window average is
    # divided by that same year's average. Price levels drift a lot between
    # years, so this measures season alone instead of mixing in the trend.
    ratios = []
    excluded: List[int] = []
    for year, grp in near.groupby("year"):
        # Baseline excludes the window itself, otherwise a strong season would
        # be diluted by its own high prices sitting inside the year average.
        rest = df[(df["year"] == year) & ~near_mask]
        if len(rest) < 20:
            continue
        # A feed change mid-year (say a new live ingest alongside an older
        # backfill) shifts price levels for reasons that are not seasonal, so a
        # year whose window and baseline come from different feeds is dropped
        # rather than averaged into the index.
        if "source" in df.columns and _feed_overlap(grp["source"], rest["source"]) < 0.75:
            excluded.append(int(year))
            continue
        base = float(rest["modal_price"].mean())
        if base > 0:
            ratios.append(float(grp["modal_price"].mean()) / base)
    if not ratios:
        return None

    index = sum(ratios) / len(ratios)
    delta_pct = (index - 1.0) * 100.0
    return {
        "month": today.strftime("%B"),
        "seasonal_index": round(index, 3),
        "month_mean": round(float(near["modal_price"].mean()), 2),
        "rest_of_year_mean": round(float(df[~near_mask]["modal_price"].mean()), 2),
        "overall_mean": round(float(df["modal_price"].mean()), 2),
        "delta_pct": round(delta_pct, 1),
        "observations": int(len(near)),
        "years": len(ratios),
        "excluded_years": excluded,
        "window_days": window * 2,
        "district": district,
        "state": state,
        "scope": scope,
    }


def supply_breadth(commodity: str, district: Optional[str] = None,
                   state: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Markets reporting is a real proxy for arrivals: when the number of mandis
    quoting a commodity falls, supply into the market has tightened.

    Snapshots in the store are not always daily, so this compares the two most
    recent reporting days within a month of each other and reports both dates.
    """
    df, scope = _scoped_history(commodity, district, state, years=1.0,
                               min_rows=30)
    if df is None:
        return None

    df = df[df["modal_price"] > 0]
    if df.empty:
        return None

    # A partial ingest day (a couple of rows) would look like a supply collapse,
    # so only days that actually covered several mandis count as snapshots.
    by_day = (df.assign(day=df["date"].dt.normalize())
                .groupby("day")["market"].nunique().sort_index())
    # Threshold against a typical full day, so a half-finished ingest does not
    # read as a supply collapse.
    typical = float(by_day.median())
    floor = max(3.0, typical * 0.5)
    usable = [d for d, n in by_day.items() if n >= floor]
    if len(usable) < 2:
        return None

    # Prefer 3 reporting days on each side so a single thin ingest day cannot
    # masquerade as a supply collapse. With fewer days, compare one to one and
    # mark the evidence weak.
    side = 3 if len(usable) >= 6 else 1
    recent_days = usable[-side:]
    prior_days = usable[-2 * side:-side]
    latest, prior_day = pd.Timestamp(recent_days[-1]), pd.Timestamp(prior_days[-1])
    gap = (latest - prior_day).days
    if gap > 35:
        return None

    # Share of reporting mandis, not a raw count: the feed itself carries more
    # or fewer markets from day to day, and a raw count would just measure that.
    baseline = price_store.daily_market_counts(
        [d.strftime("%Y-%m-%d") for d in recent_days + prior_days])

    def share(days):
        sel = df[df["date"].dt.normalize().isin(days)]
        per_day = sel.groupby(sel["date"].dt.normalize())["market"].nunique()
        values = []
        for day, n in per_day.items():
            total = baseline.get(day.strftime("%Y-%m-%d")) or 0
            if total >= 3:
                values.append(n / total)
        return sum(values) / len(values) if values else None

    recent_share = share(recent_days)
    prior_share = share(prior_days)
    if not recent_share or not prior_share:
        return None

    def avg_markets(days):
        sel = df[df["date"].dt.normalize().isin(days)]
        return float(sel.groupby(sel["date"].dt.normalize())["market"].nunique().mean())

    change_pct = (recent_share - prior_share) / prior_share * 100.0
    return {
        "markets_recent": int(round(avg_markets(recent_days))),
        "markets_prior": int(round(avg_markets(prior_days))),
        "share_recent_pct": round(recent_share * 100.0, 2),
        "share_prior_pct": round(prior_share * 100.0, 2),
        "change_pct": round(change_pct, 1),
        "window_days": gap,
        "days_compared": len(recent_days) + len(prior_days),
        "as_of": latest.strftime("%Y-%m-%d"),
        "compared_with": prior_day.strftime("%Y-%m-%d"),
        "scope": scope,
    }


# --------------------------------------------------------------------------- #
# Weather, flood risk and heat stress
# --------------------------------------------------------------------------- #

RAIN_HEAVY_MM = 64.5      # IMD "heavy rainfall" threshold for a single day
FLOOD_3DAY_MM = 115.0     # 3-day accumulation used as a flood-risk proxy
HEAT_STRESS_C = 38.0


def weather_signals(lat: Optional[float], lon: Optional[float],
                    days: int = 14) -> Optional[Dict[str, Any]]:
    """
    Real Open-Meteo forecast turned into supply-risk signals. Flood risk is a
    rainfall-threshold proxy, not a flood warning — the UI labels it as such.
    """
    if lat is None or lon is None:
        return None
    try:
        from utils.utils import get_weather_forecast
        forecast = get_weather_forecast(lat, lon, days=days)
    except Exception:
        return None
    if not forecast:
        return None

    rain = [float(f.get("precipitation") or 0.0) for f in forecast]
    tmax = [float(f.get("temp_max") or 0.0) for f in forecast]

    next7 = rain[:7]
    total_7 = sum(next7)
    max_day = max(next7) if next7 else 0.0
    # Worst 3-day rolling accumulation in the window
    three_day_max = max(
        (sum(rain[i:i + 3]) for i in range(max(1, len(rain) - 2))),
        default=0.0,
    )
    heavy_days = sum(1 for r in next7 if r >= RAIN_HEAVY_MM)
    heat_days = sum(1 for t in tmax[:7] if t >= HEAT_STRESS_C)

    flood_risk = (three_day_max >= FLOOD_3DAY_MM
                  or total_7 >= 150.0
                  or heavy_days >= 2)
    dry_spell = total_7 < 1.0

    signals: List[Dict[str, Any]] = []
    if flood_risk:
        signals.append({
            "key": "flood_risk",
            "label": "Heavy rain / flood risk",
            "direction": "up",
            "strength": "high",
            "detail": (
                f"{three_day_max:.0f} mm forecast over 3 days"
                + (f", {heavy_days} heavy-rain day(s)" if heavy_days else "")
                + " — mandi arrivals can be disrupted and road transport cut."
            ),
        })
    elif heavy_days:
        signals.append({
            "key": "heavy_rain",
            "label": "Heavy rain expected",
            "direction": "up",
            "strength": "medium",
            "detail": f"{heavy_days} day(s) at or above {RAIN_HEAVY_MM:.0f} mm in the next week.",
        })
    elif dry_spell:
        signals.append({
            "key": "dry_spell",
            "label": "Dry week",
            "direction": "neutral",
            "strength": "low",
            "detail": f"Only {total_7:.1f} mm rain forecast in 7 days — steady arrivals likely.",
        })

    if heat_days:
        signals.append({
            "key": "heat_stress",
            "label": "Heat stress",
            "direction": "up",
            "strength": "medium",
            "detail": (
                f"{heat_days} day(s) above {HEAT_STRESS_C:.0f}°C — perishable produce "
                "loses quality, so graded stock can fetch more."
            ),
        })

    if not signals:
        # Say what the weather actually is instead of showing nothing at all.
        signals.append({
            "key": "weather_normal",
            "label": "Normal weather ahead",
            "direction": "neutral",
            "strength": "low",
            "detail": (
                f"{total_7:.1f} mm rain expected over 7 days (peak day "
                f"{max_day:.0f} mm), no heavy-rain or heat thresholds crossed."
            ),
        })

    return {
        "source": "open_meteo",
        "lat": lat,
        "lon": lon,
        "total_rain_7d_mm": round(total_7, 1),
        "max_day_rain_mm": round(max_day, 1),
        "max_3day_rain_mm": round(three_day_max, 1),
        "heavy_rain_days": heavy_days,
        "heat_days": heat_days,
        "flood_risk": flood_risk,
        "signals": signals,
    }


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _monthly_seasonality(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Season index from published monthly averages, shaped like
    `seasonality()` so the same signal text can describe it.

    `info` is the forecast's own `season` block: month-of-year average divided
    by the commodity's average across all months, computed from the AGMARKNET
    district monthly analysis report.
    """
    try:
        index = float(info.get("index"))
    except (TypeError, ValueError):
        return None
    if index <= 0:
        return None
    return {
        "month": info.get("month") or "",
        "seasonal_index": round(index, 3),
        "delta_pct": round((index - 1.0) * 100.0, 1),
        "month_mean": None,
        "rest_of_year_mean": None,
        "overall_mean": None,
        "observations": int(info.get("months_used") or 0),
        "years": int(info.get("years_used") or 0),
        "excluded_years": [],
        "window_days": 0,
        "scope": "district monthly averages",
    }


def build_factors(commodity: str,
                  district: Optional[str] = None,
                  state: Optional[str] = None,
                  lat: Optional[float] = None,
                  lon: Optional[float] = None,
                  change_pct: Optional[float] = None,
                  season_index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Everything that can move this price, each with its own evidence.

    `direction` is the expected effect on price: "up" (firmer), "down"
    (softer) or "neutral". Strength reflects how confident the underlying data
    is, not how large the effect will be.

    `season_index` is the forecast's own month-of-year index from published
    monthly averages; it is used only when no daily series is dense enough to
    measure seasonality directly.
    """
    signals: List[Dict[str, Any]] = []
    sources: List[str] = []
    missing: List[str] = []

    # --- season (agronomic window) ---
    season = current_season()
    signals.append({
        "key": "season",
        "label": f"Season: {season['name']}",
        "direction": "neutral",
        "strength": "low",
        "detail": season["note"],
    })

    # --- seasonality from real prices ---
    seas = seasonality(commodity, district, state)
    if seas:
        sources.append("mandi_price_store (seasonal averages)")
    elif season_index:
        # Daily history too thin here: fall back to the published monthly
        # averages, which the forecast already computed for this month.
        seas = _monthly_seasonality(season_index)
        if seas:
            sources.append("agmarknet (district monthly averages)")
    if seas:
        if seas["delta_pct"] >= 3:
            direction, word = "up", "above"
        elif seas["delta_pct"] <= -3:
            direction, word = "down", "below"
        else:
            direction, word = "neutral", "in line with"
        signals.append({
            "key": "seasonality",
            "label": f"{seas['month']} seasonality",
            "direction": direction,
            "strength": "medium" if abs(seas["delta_pct"]) >= 10 else "low",
            "detail": (
                f"Around {seas['month']}, {commodity} trades "
                f"{abs(seas['delta_pct']):.1f}% {word} its own yearly average "
                f"(seasonal index {seas['seasonal_index']:.2f} across "
                f"{seas['years']} year(s), {seas['observations']} observations, "
                f"{seas['scope']} scope"
                + (f"; {len(seas['excluded_years'])} year(s) left out because the "
                   "reporting feed changed mid-year"
                   if seas.get("excluded_years") else "")
                + ")."
            ),
        })
    else:
        missing.append("seasonality (not enough history for this month)")

    # --- supply breadth ---
    supply = supply_breadth(commodity, district, state)
    if supply:
        sources.append("mandi_price_store (market breadth)")
        ch = supply["change_pct"]
        # A one-day-to-one-day comparison is weak evidence, so it never earns
        # more than "low" confidence.
        solid = supply["days_compared"] >= 4
        if ch <= -15:
            direction, strength = "up", ("medium" if solid else "low")
            word = "fewer"
        elif ch >= 15:
            direction, strength = "down", ("medium" if solid else "low")
            word = "more"
        else:
            direction, strength = "neutral", "low"
            word = "about the same share"
        signals.append({
            "key": "supply",
            "label": "Market supply",
            "direction": direction,
            "strength": strength,
            "detail": (
                (f"Averaging the latest {supply['days_compared'] // 2} reporting "
                 f"days to {supply['as_of']} against the {supply['days_compared'] // 2} "
                 f"before {supply['compared_with']}, " if supply["days_compared"] > 2
                 else f"Between {supply['compared_with']} and {supply['as_of']}, ")
                + f"{word} of the reporting mandis quoted {commodity} "
                f"({supply['share_recent_pct']:.1f}% vs "
                f"{supply['share_prior_pct']:.1f}% of all mandis, "
                f"{supply['markets_recent']} vs {supply['markets_prior']} markets "
                f"a day, {ch:+.1f}%, {supply['scope']} scope)."
            ),
        })
    else:
        missing.append("supply breadth (no comparable market windows)")

    # --- weather / flood / heat ---
    weather = weather_signals(lat, lon)
    if weather:
        sources.append("open_meteo (14-day forecast)")
        signals.extend(weather["signals"])
    else:
        missing.append("weather (no coordinates for this district)")

    # --- festivals ---
    fests = upcoming_festivals(days_ahead=21)
    if fests:
        sources.append("festival calendar (lunar dates approximate)")
        nxt = fests[0]
        signals.append({
            "key": "festival",
            "label": f"{nxt['name']} in {nxt['days_until']} day(s)",
            "direction": "up" if nxt["days_until"] <= 14 else "neutral",
            "strength": "medium" if nxt["days_until"] <= 14 else "low",
            "detail": (
                "Festival demand can lift prices for fruit, vegetables and "
                "pulses in the run-up. Whether it does here is measured on this "
                "crop's own past festival prices, and an adjustment is applied "
                "only when that effect is larger than normal week-to-week noise."
                + (" Date is approximate — lunar calendars vary by region."
                   if nxt["approx"] else "")
            ),
            "festivals": [
                {"name": f["name"], "date": f["date"], "days_until": f["days_until"],
                 "approx": f["approx"]}
                for f in fests
            ],
        })

    # --- unexpected shocks ---
    shocks: List[str] = []
    if weather and weather["flood_risk"]:
        shocks.append(
            "Heavy-rain/flood risk in the forecast window can spike prices "
            "within days as arrivals stop."
        )
    if supply and supply["change_pct"] <= -30 and supply["days_compared"] >= 4:
        shocks.append(
            "Market participation has dropped sharply — a sudden supply gap is "
            "possible."
        )

    up = sum(1 for s in signals if s["direction"] == "up")
    down = sum(1 for s in signals if s["direction"] == "down")
    tilt = "firm" if up > down else "soft" if down > up else "balanced"

    summary_parts = []
    if change_pct is not None:
        summary_parts.append(f"The model expects {change_pct:+.1f}% over 14 days.")
    summary_parts.append(
        f"{up} factor(s) point to firmer prices and {down} to softer; "
        f"overall tilt is {tilt}."
    )
    if shocks:
        summary_parts.append("Risk: " + " ".join(shocks))

    return {
        "commodity": commodity,
        "district": district,
        "state": state,
        "as_of": datetime.now().strftime("%Y-%m-%d"),
        "tilt": tilt,
        "up_count": up,
        "down_count": down,
        "signals": signals,
        "shocks": shocks,
        "summary": " ".join(summary_parts),
        "season": season,
        "weather": weather,
        "festivals": fests,
        "seasonality": seas,
        "supply": supply,
        "sources": sources,
        "unavailable": missing,
        "disclaimer": (
            "These are context factors, not inputs to the price model. The forecast "
            "itself comes from Holt-Winters on observed mandi prices. Flood risk is a "
            "rainfall-threshold indicator, not an official flood warning."
        ),
    }
