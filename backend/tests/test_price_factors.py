"""
Guard tests for the price *context* factors.

The forecast comes from Holt-Winters on real mandi prices. These tests cover the
signals layered around it — season, seasonality, supply breadth, weather/flood
risk and festivals — and enforce the rule that shaped the module: every signal
is derived from a real input, and an input that is missing is reported as
missing rather than replaced with a guess.

Run from the repo root:
    ./collab/venv/bin/python -m pytest Farm_intel/backend/tests -q
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import price_factors  # noqa: E402


# --------------------------------------------------------------------------- #
# Calendar helpers
# --------------------------------------------------------------------------- #

def test_window_handles_year_wrap():
    # A window that crosses the new year: 1 Dec -> 31 Jan
    assert price_factors._in_window(date(2026, 12, 15), 12, 1, 1, 31)
    assert price_factors._in_window(date(2026, 1, 5), 12, 1, 1, 31)
    assert not price_factors._in_window(date(2026, 6, 5), 12, 1, 1, 31)

    # A window inside one year must not wrap: 1 Oct -> 30 Nov
    assert price_factors._in_window(date(2026, 11, 2), 10, 1, 11, 30)
    assert not price_factors._in_window(date(2026, 1, 5), 10, 1, 11, 30)


def test_current_season_names_real_window():
    season = price_factors.current_season(date(2026, 11, 2))
    assert season["name"] == "Kharif harvest"
    assert season["window"]


def test_upcoming_festivals_are_sorted_and_bounded():
    today = date(2026, 10, 25)
    fests = price_factors.upcoming_festivals(days_ahead=21, on=today)
    assert fests, "Diwali should fall inside a 21-day horizon from 2026-10-25"
    days = [f["days_until"] for f in fests]
    assert days == sorted(days)
    assert all(0 <= d <= 21 for d in days)
    assert all(
        (date.fromisoformat(f["date"]) - today).days == f["days_until"] for f in fests
    )


def test_upcoming_festivals_empty_outside_horizon():
    assert price_factors.upcoming_festivals(days_ahead=1, on=date(2026, 7, 1)) == []


# --------------------------------------------------------------------------- #
# Seasonality — must be an index, not a raw price gap
# --------------------------------------------------------------------------- #

def _year_frame(year: int, base: float, window_price: float,
                source: str = "agmarknet_backfill",
                window_source: str | None = None) -> pd.DataFrame:
    """A year of prices at `base`, elevated inside the same window the module uses."""
    target = date.today().timetuple().tm_yday
    rows = []
    day = date(year, 1, 1)
    while day.year == year:
        diff = abs(day.timetuple().tm_yday - target)
        in_window = diff <= 15 or diff >= 365 - 15
        rows.append({
            "date": pd.Timestamp(day),
            "market": f"M{day.timetuple().tm_yday % 7}",
            "modal_price": window_price if in_window else base,
            "source": (window_source or source) if in_window else source,
        })
        day += timedelta(days=2)
    return pd.DataFrame(rows)


def test_seasonality_is_a_seasonal_index(monkeypatch):
    # 2024 trades at 100/120, 2025 at 200/240 — the same +20% season at double
    # the price level. A raw price gap would report ~+46%; the index must say
    # +20%, because it divides each year by that same year's own average.
    def index_for(df):
        monkeypatch.setattr(price_factors.price_store, "history",
                            lambda *a, **k: df.copy())
        seas = price_factors.seasonality("Onion", "Kolar", "Karnataka")
        assert seas is not None
        assert seas["excluded_years"] == []
        return seas

    flat = index_for(pd.concat([_year_frame(2024, 100.0, 120.0),
                                _year_frame(2025, 100.0, 120.0)]))
    shifted = index_for(pd.concat([_year_frame(2024, 100.0, 120.0),
                                   _year_frame(2025, 200.0, 240.0)]))

    assert flat["seasonal_index"] == pytest.approx(1.2, abs=0.02)
    assert flat["delta_pct"] == pytest.approx(20.0, abs=2.0)
    assert shifted["seasonal_index"] == pytest.approx(flat["seasonal_index"], abs=0.02)
    assert flat["years"] == 2 and shifted["years"] == 2


def test_seasonality_drops_year_whose_feed_changed(monkeypatch):
    # A live ingest can start mid-year at a completely different price level.
    # That year's window is not comparable with its own baseline, so it must be
    # excluded instead of producing a fake season.
    df = pd.concat([
        _year_frame(2024, 100.0, 120.0),
        _year_frame(2025, 100.0, 120.0),
        _year_frame(date.today().year, 1000.0, 5000.0,
                    source="agmarknet_backfill", window_source="agmarknet_live"),
    ])
    monkeypatch.setattr(price_factors.price_store, "history",
                        lambda *a, **k: df.copy())
    seas = price_factors.seasonality("Onion", "Kolar", "Karnataka")
    assert seas is not None
    assert seas["years"] == 2
    assert seas["excluded_years"] == [date.today().year]
    assert seas["seasonal_index"] == pytest.approx(1.2, abs=0.02)


def test_seasonality_returns_none_without_history(monkeypatch):
    monkeypatch.setattr(price_factors.price_store, "history",
                        lambda *a, **k: pd.DataFrame())
    assert price_factors.seasonality("Onion", "Kolar", "Karnataka") is None


def test_seasonality_skips_thin_district_for_wider_scope(monkeypatch):
    thin = _year_frame(2025, base=100.0, window_price=120.0).head(3)
    wide = pd.concat([
        _year_frame(2024, base=100.0, window_price=120.0),
        _year_frame(2025, base=100.0, window_price=120.0),
    ])

    def fake_history(commodity, district=None, state=None, years=2.0):
        return thin.copy() if district else (wide.copy() if not state else wide.copy())

    monkeypatch.setattr(price_factors.price_store, "history", fake_history)
    seas = price_factors.seasonality("Onion", "Kolar", "Karnataka")
    assert seas is not None, "a 3-row district must not block a usable wider scope"
    assert seas["scope"] in {"state", "national"}
    assert seas["observations"] > 3


# --------------------------------------------------------------------------- #
# Supply breadth — share of reporting mandis, not a raw count
# --------------------------------------------------------------------------- #

def _supply_frame(per_day_markets) -> pd.DataFrame:
    rows = []
    start = date(2026, 10, 1)
    for d, n in enumerate(per_day_markets):
        day = start + timedelta(days=d)
        for m in range(n):
            rows.append({
                "date": pd.Timestamp(day),
                "market": f"Market{m}",
                "modal_price": 1000.0,
            })
    return pd.DataFrame(rows)


def _wire_supply(monkeypatch, per_day_markets, per_day_totals):
    """Feed is day-indexed so the baseline never depends on call order."""
    start = date(2026, 10, 1)
    baseline = {
        (start + timedelta(days=d)).strftime("%Y-%m-%d"): n
        for d, n in enumerate(per_day_totals)
    }
    df = _supply_frame(per_day_markets)
    monkeypatch.setattr(price_factors.price_store, "history",
                        lambda *a, **k: df.copy())
    monkeypatch.setattr(price_factors.price_store, "daily_market_counts",
                        lambda days: {d: baseline[d] for d in days if d in baseline})
    return price_factors.supply_breadth("Onion", "Kolar", "Karnataka")


def test_supply_share_holds_when_whole_feed_shrinks(monkeypatch):
    # 10 of 100 mandis, then 5 of 50: the raw count halves (an ingest artifact
    # like the real Oct 27 -> Oct 29 drop), but onion's share of the market is
    # unchanged, so supply must read as flat.
    supply = _wire_supply(monkeypatch,
                          per_day_markets=[10, 10, 10, 5, 5, 5],
                          per_day_totals=[100, 100, 100, 50, 50, 50])
    assert supply is not None
    assert supply["markets_prior"] == 10
    assert supply["markets_recent"] == 5
    assert supply["change_pct"] == pytest.approx(0.0, abs=0.01)
    assert supply["share_prior_pct"] == pytest.approx(10.0, abs=0.1)
    assert supply["share_recent_pct"] == pytest.approx(10.0, abs=0.1)


def test_supply_reports_share_change_when_participation_falls(monkeypatch):
    # Same feed size, half the mandis stop quoting onion -> share halves.
    supply = _wire_supply(monkeypatch,
                          per_day_markets=[10, 10, 10, 5, 5, 5],
                          per_day_totals=[100] * 6)
    assert supply is not None
    assert supply["change_pct"] == pytest.approx(-50.0, abs=1.0)
    assert supply["share_recent_pct"] == pytest.approx(5.0, abs=0.1)
    assert supply["share_prior_pct"] == pytest.approx(10.0, abs=0.1)


def test_supply_ignores_partial_ingest_day(monkeypatch):
    # A day with a single row is an ingest artifact, not a supply collapse, so
    # it must not be picked as the "latest snapshot".
    supply = _wire_supply(monkeypatch,
                          per_day_markets=[20, 20, 20, 20, 20, 20, 1],
                          per_day_totals=[100] * 7)
    assert supply is not None
    assert supply["as_of"] == "2026-10-06"


# --------------------------------------------------------------------------- #
# Assembly — missing inputs are reported, never invented
# --------------------------------------------------------------------------- #

def test_build_factors_without_any_input_reports_gaps(monkeypatch):
    monkeypatch.setattr(price_factors.price_store, "history",
                        lambda *a, **k: pd.DataFrame())
    # No coordinates -> weather is skipped without a network call
    ctx = price_factors.build_factors("Onion", None, None, None, None, -3.5)

    keys = {s["key"] for s in ctx["signals"]}
    assert "season" in keys
    assert "weather" not in {k for k in keys if k.startswith("weather")}
    assert any("weather" in m for m in ctx["unavailable"])
    assert any("seasonality" in m for m in ctx["unavailable"])
    assert ctx["weather"] is None
    assert "-3.5%" in ctx["summary"]


def test_build_factors_counts_directions_consistently(monkeypatch):
    monkeypatch.setattr(price_factors.price_store, "history",
                        lambda *a, **k: pd.DataFrame())
    ctx = price_factors.build_factors("Onion", None, None, None, None, None)
    assert ctx["up_count"] == sum(1 for s in ctx["signals"] if s["direction"] == "up")
    assert ctx["down_count"] == sum(1 for s in ctx["signals"] if s["direction"] == "down")
    assert ctx["tilt"] in {"firm", "soft", "balanced"}


def test_build_factors_surfaces_flood_shock(monkeypatch):
    monkeypatch.setattr(price_factors.price_store, "history",
                        lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(price_factors, "weather_signals", lambda lat, lon, days=14: {
        "source": "open_meteo", "lat": lat, "lon": lon,
        "total_rain_7d_mm": 190.0, "max_day_rain_mm": 70.0,
        "max_3day_rain_mm": 160.0, "heavy_rain_days": 2, "heat_days": 0,
        "flood_risk": True,
        "signals": [{"key": "flood_risk", "label": "Heavy rain / flood risk",
                     "direction": "up", "strength": "high", "detail": "160 mm/3d"}],
    })
    ctx = price_factors.build_factors("Onion", "Kolar", "Karnataka", 13.13, 78.13, 5.0)

    assert any("flood" in s.lower() for s in ctx["shocks"])
    assert any(s["key"] == "flood_risk" for s in ctx["signals"])
    assert "Risk:" in ctx["summary"]
    assert ctx["up_count"] >= 1


def test_weather_signals_flag_flood_on_heavy_forecast(monkeypatch):
    days = [{"date": f"2026-11-{i + 1:02d}", "temp_max": 30.0, "temp_min": 22.0,
             "precipitation": 60.0 if i < 3 else 0.0, "humidity": 80.0}
            for i in range(14)]
    import utils.utils as utils_mod
    monkeypatch.setattr(utils_mod, "get_weather_forecast", lambda *a, **k: days)

    weather = price_factors.weather_signals(13.13, 78.13)
    assert weather is not None
    assert weather["flood_risk"] is True
    assert any(s["key"] in {"flood_risk", "heavy_rain"} for s in weather["signals"])


def test_weather_signals_say_when_nothing_is_happening(monkeypatch):
    days = [{"date": f"2026-11-{i + 1:02d}", "temp_max": 30.0, "temp_min": 22.0,
             "precipitation": 1.0, "humidity": 70.0}
            for i in range(14)]
    import utils.utils as utils_mod
    monkeypatch.setattr(utils_mod, "get_weather_forecast", lambda *a, **k: days)

    weather = price_factors.weather_signals(13.13, 78.13)
    assert weather is not None
    assert weather["flood_risk"] is False
    assert [s["key"] for s in weather["signals"]] == ["weather_normal"]
