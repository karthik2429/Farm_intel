"""
Accuracy and edge-case guards for the price model.

Three promises this file holds the forecaster to:

1. **Never worse than doing nothing.** `naive` (repeat today's price) is a
   candidate model, so the selected model's backtest error must not exceed the
   naive error on the same folds. Before this, a fixed Holt-Winters lost to
   naive on ~85% of folds.
2. **Corrupt rows never reach the fit.** AGMARKNET ships occasional rows in the
   wrong unit (Rs/kg next to Rs/quintal); those are repaired, counted, and the
   count is reported.
3. **Edge cases move the forecast only when measured.** Festivals, floods and
   heat are calibrated on the store's own history; an effect inside the
   series' noise is reported and *not* applied, and no factor can move the
   point estimate beyond its cap.

Run from the repo root:
    ./collab/venv/bin/python -m pytest Farm_intel/backend/tests/test_forecast_accuracy.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import price_forecast as pf  # noqa: E402
import price_store  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Selection can never lose to the naive baseline
# ---------------------------------------------------------------------------

def _rich_series():
    """The store's densest district+commodity series."""
    price_store.init_db()
    with price_store._lock:
        conn = price_store._connect()
        row = conn.execute(
            "SELECT state, district, commodity FROM mandi_prices "
            "WHERE state != '' AND district != '' GROUP BY state, district, commodity "
            "ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
    if not row:
        pytest.skip("price store is empty")
    df = price_store.history(row["commodity"], district=row["district"],
                             state=row["state"])
    g = pf._daily_grid(df.groupby("date")["modal_price"].median().sort_index())
    return pf.clean_series(g)[0]


def test_selected_model_is_never_worse_than_naive():
    g = _rich_series()
    scores = pf._model_scores(g)
    assert "naive" in scores, "the naive baseline must be a scored candidate"
    name, mape = pf._select_model(scores)
    assert mape <= scores["naive"]["mape"] + 0.01, (
        f"selected {name} at {mape}% is worse than naive "
        f"at {scores['naive']['mape']}% — selection is broken")


def test_every_candidate_is_scored():
    g = _rich_series()
    scores = pf._model_scores(g)
    assert set(scores) <= set(pf.MODELS)
    for name, s in scores.items():
        assert s["folds"] > 0, f"{name} reported scores without folds"
        assert np.isfinite(s["mape"])


# ---------------------------------------------------------------------------
# 2. Corrupt rows are repaired, not fitted
# ---------------------------------------------------------------------------

def _ramp_series(n: int = 200, level: float = 2000.0) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.Series(level + np.linspace(0, 200, n), index=idx)


def test_single_unit_error_row_is_repaired():
    g = _ramp_series()
    g.iloc[100] = g.iloc[100] / 100.0  # Rs/quintal row that is really Rs/kg
    cleaned, repaired = pf.clean_series(g)
    assert repaired == 1
    assert abs(cleaned.iloc[100] - g.iloc[100] * 100) < 50


def test_sustained_wrong_unit_stretch_is_repaired():
    """A long stretch in the wrong unit fools the rolling median; the global
    level check has to catch it."""
    g = _ramp_series()
    g.iloc[120:150] = g.iloc[120:150] * 50
    cleaned, repaired = pf.clean_series(g)
    assert repaired >= 30
    assert cleaned.iloc[120:150].max() < g.iloc[120:150].min()


def test_clean_series_leaves_good_data_alone():
    g = _ramp_series()
    cleaned, repaired = pf.clean_series(g)
    assert repaired == 0
    pd.testing.assert_series_equal(cleaned, g, check_freq=False)


def test_forecast_reports_data_quality():
    g = _rich_series()
    scores = pf._model_scores(g)
    assert scores  # sanity
    # A full forecast run carries the repair count and the model it chose.
    e = pf.forecast(district="North Goa", commodity="Onion", state="Goa")
    if not e:
        pytest.skip("no forecast for the chosen scope")
    assert "repaired_rows" in e[0]["data_quality"]
    assert e[0]["model"] in pf.MODELS
    assert e[0]["mape"] is not None


# ---------------------------------------------------------------------------
# 3. Festivals: applied only when measured and significant
# ---------------------------------------------------------------------------

def _fest(names=("Diwali",), days=5):
    return [{"name": n, "date": "2026-11-08", "approx": True,
             "region": "national", "days_until": days} for n in names]


@pytest.fixture()
def festival_only(monkeypatch):
    """Isolate the event layer from the real calendar and weather."""
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: _fest())
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: None)
    return monkeypatch


def test_significant_festival_effect_is_applied_and_bounded(festival_only):
    festival_only.setattr(pf, "festival_calibration", lambda *a, **k: {
        "events": 12, "uplift_pct": 3.0, "t_stat": 2.4, "significant": True,
        "median_festival_7d_pct": 2.0, "baseline_7d_pct": -1.0,
    })
    layer = pf._event_layer("Onion", "North Goa", "Goa", None)
    assert layer["applied"], "a significant measured effect should be applied"
    shift = layer["applied"][0]["shift_pct"]
    assert 0 < shift <= pf.FESTIVAL_SHIFT_CAP * 100
    assert "measured" in layer["applied"][0]["evidence"]
    assert layer["band_mult"] > 1.0


def test_festival_effect_inside_the_noise_is_not_applied(festival_only):
    """The honest case: the calendar says festival, the data says no effect."""
    festival_only.setattr(pf, "festival_calibration", lambda *a, **k: {
        "events": 26, "uplift_pct": 1.81, "t_stat": 0.74, "significant": False,
        "median_festival_7d_pct": 1.25, "baseline_7d_pct": -0.56,
    })
    layer = pf._event_layer("Onion", "North Goa", "Goa", None)
    assert layer["applied"] == []
    assert layer["shift_total_pct"] == 0.0
    assert any("noise" in n for n in layer["notes"])


def test_festival_without_calibration_is_not_guessed(festival_only):
    festival_only.setattr(pf, "festival_calibration", lambda *a, **k: None)
    layer = pf._event_layer("Onion", "North Goa", "Goa", None)
    assert layer["applied"] == []
    assert any("too few past festivals" in n for n in layer["notes"])


# ---------------------------------------------------------------------------
# 4. Flood / disaster / heat triggers
# ---------------------------------------------------------------------------

def _trigger(key="flood_risk"):
    return {"flood_risk": key == "flood_risk", "signals": [{"key": key}]}


def test_flood_trigger_moves_estimate_within_the_cap(monkeypatch):
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: [])
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: {
        "up_events": 9, "down_events": 4, "after_spike_14d_pct": 12.0,
        "after_crash_14d_pct": -5.0, "baseline_14d_pct": 0.0,
        "t_stat": 2.5, "significant": True,
    })
    layer = pf._event_layer("Onion", "North Goa", "Goa", _trigger())
    assert layer["applied"], "a significant shock response should be applied"
    assert 0 < layer["shift_total_pct"] <= pf.EVENT_SHIFT_CAP * 100
    assert layer["band_mult"] >= pf.BAND_WIDEN_EVENT
    # The shift builds in over the first days, it does not appear on day 1.
    assert layer["shifts"][0] < layer["shifts"][-1]


def test_uncalibrated_flood_widens_band_without_inventing_a_shift(monkeypatch):
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: [])
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: None)
    layer = pf._event_layer("Onion", "North Goa", "Goa", _trigger())
    assert layer["shift_total_pct"] == 0.0
    assert layer["band_mult"] >= pf.BAND_WIDEN_EVENT
    assert any("band is widened" in n for n in layer["notes"])


def test_heat_trigger_is_recognised(monkeypatch):
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: [])
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: None)
    layer = pf._event_layer("Onion", "North Goa", "Goa", _trigger("heat_stress"))
    assert layer["band_mult"] >= pf.BAND_WIDEN_EVENT


def test_no_trigger_no_event_shift(monkeypatch):
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: [])
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: None)
    layer = pf._event_layer("Onion", "North Goa", "Goa", None)
    assert layer["shift_total_pct"] == 0.0
    assert layer["band_mult"] == 1.0


def test_total_shift_never_exceeds_cap(monkeypatch):
    """Festival plus flood together must still be one bounded adjustment."""
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: _fest())
    monkeypatch.setattr(pf, "festival_calibration", lambda *a, **k: {
        "events": 12, "uplift_pct": 4.0, "t_stat": 3.0, "significant": True,
        "median_festival_7d_pct": 4.0, "baseline_7d_pct": 0.0,
    })
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: {
        "up_events": 9, "down_events": 3, "after_spike_14d_pct": 20.0,
        "after_crash_14d_pct": -9.0, "baseline_14d_pct": 0.0,
        "t_stat": 4.0, "significant": True,
    })
    layer = pf._event_layer("Onion", "North Goa", "Goa", _trigger())
    assert abs(layer["shift_total_pct"]) <= pf.EVENT_SHIFT_CAP * 100 + 1e-9


# ---------------------------------------------------------------------------
# 5. The advice text tells the truth about confidence
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 6. Monthly-average districts: 14 days, flat carry, rain-aware
# ---------------------------------------------------------------------------

@pytest.fixture()
def monthly_grid():
    """A monthly series shaped like the published AGMARKNET averages."""
    months = pd.date_range("2024-01-01", periods=30, freq="MS")
    prices = 2000 + 300 * np.sin(np.arange(30) / 2.0) + np.arange(30) * 12
    df = pd.DataFrame({"date": months, "price": prices})
    return df, pf.monthly_to_daily(df)


def test_monthly_basis_never_uses_a_trend_model(monthly_grid):
    """Measured on 420 forecasts: a trend fitted to interpolated monthly
    averages raises the median 14-day error from 10.6% to ~13.5%."""
    _df, grid = monthly_grid
    name, fc, _mape, _scores, _dg = pf.select_and_forecast(
        grid, 14, stale_days=15, basis="monthly")
    assert name in ("naive", "seasonal_naive"), \
        f"monthly basis picked {name}, which overshoots on interpolated data"
    assert len(fc) == 14


def test_stale_series_drops_the_trend():
    """With months-old data a trend is extrapolating an unconfirmed level."""
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    g = pd.Series(2000 + np.arange(200) * 8.0, index=idx)
    name, _fc, _m, _s, downgraded = pf.select_and_forecast(
        g, 14, stale_days=200, basis="daily")
    assert not name.startswith("hw"), f"stale series kept {name}"
    assert downgraded is True


def test_monthly_forecast_is_fourteen_days():
    """A monthly-basis district still answers with a 14-day trajectory."""
    e = pf.forecast(district="Nagpur", commodity="Tomato", state="Maharashtra")
    if not e:
        pytest.skip("no monthly history for this scope")
    entry = e[0]
    assert entry["history_basis"] == "monthly"
    assert len(entry["trajectory"]) == 14
    assert [p["day"] for p in entry["trajectory"]] == list(range(1, 15))
    assert entry["model"] in ("naive", "seasonal_naive")


def test_rain_effect_removes_season_before_measuring(monkeypatch):
    """Rain must be measured after removing month-of-year, otherwise a rainy
    month is just a monsoon month and the season index gets counted twice."""
    months = pd.date_range("2024-01-01", periods=24, freq="MS")
    season = np.array([1.0, 1.1, 1.2, 1.0, 0.9, 0.8,
                       0.8, 0.9, 1.0, 1.1, 1.2, 1.1] * 2)
    rain_mm = {f"{y}-{m:02d}": (120.0 if m in (6, 7, 8) else 5.0)
               for y in (2024, 2025) for m in range(1, 13)}
    df = pd.DataFrame({"date": months, "price": 1000 * season})

    monkeypatch.setattr(pf.price_store, "monthly_history", lambda *a, **k: df)
    import rainfall as rain_mod
    monkeypatch.setattr(rain_mod, "monthly_rainfall", lambda *a, **k: rain_mm)
    monkeypatch.setattr(rain_mod, "month_to_date", lambda *a, **k: 5.0)

    eff = pf.rain_effect("Tomato", "Nagpur", "Maharashtra", 21.15, 79.01,
                         target_month=11)
    assert eff is not None
    # Prices here depend only on the calendar, so after removing the month and
    # year means there is no rain signal left to find.
    assert abs(eff["slope_pct_per_ratio"] or 0) < 8
    assert eff["months_used"] == 24


def test_rain_effect_needs_two_sigma_to_apply():
    """A weak slope must be reported, not applied."""
    eff = pf.rain_effect("Tomato", "Nagpur", "Maharashtra", 21.15, 79.01)
    if eff is None:
        pytest.skip("no monthly history / rain cache for this scope")
    if not eff["significant"]:
        layer = pf._event_layer("Tomato", "Nagpur", "Maharashtra", None,
                                lat=21.15, lon=79.01)
        assert not any(a["key"] == "rainfall" for a in layer["applied"])


def test_rain_adjustment_is_bounded(monkeypatch):
    import price_factors
    monkeypatch.setattr(price_factors, "upcoming_festivals", lambda **_: [])
    monkeypatch.setattr(pf, "shock_response", lambda *a, **k: None)
    monkeypatch.setattr(pf, "rain_effect", lambda *a, **k: {
        "months_used": 24, "slope_pct_per_ratio": 60.0, "t_stat": 4.0,
        "current_ratio": 2.0, "current_month_mm": 120.0, "normal_mm": 60.0,
        "normal_years": 2, "current_month": 7,
        "expected_shift_pct": 60.0, "significant": True,
    })
    layer = pf._event_layer("Tomato", "Nagpur", "Maharashtra", None,
                            lat=21.15, lon=79.01)
    assert layer["shift_total_pct"] <= pf.EVENT_SHIFT_CAP * 100 + 1e-9
    assert any(a["key"] == "rainfall" for a in layer["applied"])


def test_low_confidence_signal_does_not_give_sell_advice():
    text = pf._signal_text(-8.0, mape=30.0)
    assert "Low confidence" in text
    assert "consider selling" not in text


def test_confident_signal_still_advises():
    text = pf._signal_text(-8.0, mape=4.0)
    assert "consider selling" in text
