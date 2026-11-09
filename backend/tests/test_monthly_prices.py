"""
Guards for the AGMARKNET district monthly backfill.

The report behind https://agmarknet.gov.in/districtwholesalemonthanalysis
returns, for one commodity+state+year+month, a row per district with three
published averages: the requested month, the previous month and the same month
a year earlier. Those numbers are what let a state with no daily feed still get
a real two-year history.

These tests run on a throwaway SQLite file so they never touch the live store.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import agmarknet_monthly  # noqa: E402
import mandi_prices  # noqa: E402
import price_forecast  # noqa: E402
import price_store  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A private monthly store, plus a clean forecast cache."""
    monkeypatch.setattr(price_store, "DB_PATH", str(tmp_path / "monthly.db"))
    monkeypatch.setattr(price_store, "_conn", None)
    monkeypatch.setattr(price_forecast, "_cache", {})
    price_store.init_db()
    yield price_store
    monkeypatch.setattr(price_store, "_conn", None)


def seed(store, state="Testland", district="Testpur", commodity="Tomato",
         months=26, with_shock=True):
    """Published-average shaped rows: gentle trend, Oct/Nov peak, one spike."""
    rows = []
    start = pd.Timestamp("2024-01-01")
    for i in range(months):
        d = start + pd.offsets.MonthBegin(i)
        price = 1500 + 25 * i
        if d.month in (10, 11):
            price *= 1.35
        if with_shock and d.year == 2025 and d.month == 7:
            price *= 1.6
        rows.append({"state": state, "district": district, "commodity": commodity,
                     "year": int(d.year), "month": int(d.month),
                     "price": round(price, 2), "source": "agmarknet_monthly"})
    assert store.monthly_upsert_many(rows) == len(rows)
    return rows


# --------------------------------------------------------------------------- #
# Report parsing
# --------------------------------------------------------------------------- #

def test_parse_rows_keeps_all_three_published_months():
    """One response carries this month, last month and the same month a year
    earlier — all three must be read, and the 'Average' footer skipped."""
    rows = [
        {"district": "Pune", "prices_december_2024": 1358.75,
         "prices_november_2024": 1925.71, "prices_december_2023": 1410.58,
         "change_over_previous_month": "-29.4"},
        {"district": "Average", "prices_december_2024": 1779.18,
         "prices_november_2024": 2255.09, "prices_december_2023": 1691.37},
        {"district": "Kolhapur", "prices_december_2024": "-",
         "prices_november_2024": 1400.0, "prices_december_2023": None},
    ]
    parsed = agmarknet_monthly.parse_rows(rows, month=12, year=2024)
    assert ("Pune", 2024, 12, 1358.75) in parsed
    assert ("Pune", 2024, 11, 1925.71) in parsed
    assert ("Pune", 2023, 12, 1410.58) in parsed
    # footer row is not a district
    assert all(d != "Average" for d, _y, _m, _p in parsed)
    # "-" and null cells are dropped, not turned into 0
    assert all(p > 0 for _d, _y, _m, p in parsed)
    assert ("Kolhapur", 2024, 11, 1400.0) in parsed


def test_month_window_is_dense_for_two_years():
    """Requesting only the current year still covers two years, because every
    response also returns the previous month and the same month last year."""
    year = pd.Timestamp.today().year
    pairs = agmarknet_monthly.months_window([year])
    assert pairs, "no months to request"
    assert pairs[0] == (year, pd.Timestamp.today().month)  # newest first
    covered = set(pairs)
    for y, m in pairs:
        covered.add((y, m - 1) if m > 1 else (y - 1, 12))
        covered.add((y - 1, m))
    months = {(y, m) for y, m in covered if y}
    assert len(months) >= 24, f"window only covers {len(months)} months"


# --------------------------------------------------------------------------- #
# Store shapes
# --------------------------------------------------------------------------- #

def test_monthly_history_is_one_row_per_month(store):
    seed(store, months=26)
    df = store.monthly_history("Tomato", state="Testland")
    assert len(df) == 26
    assert df["date"].is_monotonic_increasing
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-01")
    assert df["date"].iloc[-1] == pd.Timestamp("2026-02-01")
    assert (df["price"] > 0).all()


def test_monthly_history_matches_alternate_state_spellings(store):
    """The UI says Kerala/Puducherry; AGMARKNET publishes Keralam/Pondicherry."""
    seed(store, state="Pondicherry", district="Karaikal", months=14)
    assert len(store.monthly_history("Tomato", state="Puducherry")) == 14


def test_monthly_only_district_resolves_its_state(store):
    seed(store, months=14)
    assert store.state_for_district("Testpur") == "Testland"


def test_distinct_commodities_includes_monthly_only_crops(store):
    seed(store, commodity="Brinjal", months=14)
    names = store.distinct_commodities(state="Testland", allow_any=False)
    assert "Brinjal" in names


def test_months_present_supports_resume(store):
    seed(store, months=14)
    present = store.monthly_months_present("Testland", "Tomato")
    assert (2024, 1) in present and (2025, 2) in present
    assert (2025, 3) not in present


# --------------------------------------------------------------------------- #
# Forecast on a monthly-only state
# --------------------------------------------------------------------------- #

def test_state_forecast_uses_monthly_averages(store):
    seed(store, months=26)
    out = price_forecast.forecast(None, "Tomato", "All", state="Testland")
    assert out, "no forecast from two years of published monthly averages"
    e = out[0]
    assert e["history_basis"] == "monthly"
    assert e["scope_level"] == "state"
    assert e["district"] is None
    assert len(e["trajectory"]) == 14
    assert e["history_months"] >= 24
    # monthly series is labelled by month, not by an invented mid-month date
    assert len(e["history_last"]) == 7


def test_forecast_exposes_season_festivals_and_shocks(store):
    seed(store, months=26)
    e = price_forecast.forecast(None, "Tomato", "All", state="Testland")[0]
    assert e["season"] is not None
    assert 0.5 < e["season"]["index"] < 2.0
    assert e["season"]["years_used"] >= 2
    assert isinstance(e["festivals"], list)
    # the seeded July spike must show up as a measured swing
    assert any("2025" in s for s in e["shocks"]), e["shocks"]
    assert 0.8 < e["adjustment"] < 1.25


def test_season_index_tilts_october_november_up(store):
    """Seasonality is measured, so the seeded Oct/Nov peak must lift the
    adjustment instead of being flattened away."""
    seed(store, months=26)
    e = price_forecast.forecast(None, "Tomato", "All", state="Testland")[0]
    oct_nov = [y for y in (2024, 2025) for m in (10, 11) if True]
    df = store.monthly_history("Tomato", state="Testland")
    df["month"] = df["date"].dt.month
    peak = float(df[df["month"].isin((10, 11))]["price"].mean())
    rest = float(df[~df["month"].isin((10, 11))]["price"].mean())
    assert peak > rest, "seed is not seasonal"
    assert e["season"]["raw_index"] > 1.0
    assert oct_nov  # keep the intent readable


def test_district_forecast_uses_its_own_monthly_averages(store):
    """A district with published averages gets a district-level forecast, not
    the state aggregate."""
    seed(store, months=26)
    seed(store, district="Otherpur", months=26)
    e = price_forecast.forecast("Testpur", "Tomato", "All", state="Testland")[0]
    assert e["scope_level"] == "district"
    assert e["district"] == "Testpur"
    assert e["history_basis"] == "monthly"
    assert e["history_months"] >= 24


def test_district_forecast_matches_alternate_spelling(store):
    seed(store, district="Belgaum", months=26)
    e = price_forecast.forecast("Belagavi", "Tomato", "All", state="Testland")[0]
    assert e["scope_level"] == "district"


def test_district_without_history_says_it_is_a_state_estimate(store):
    seed(store, months=26)
    e = price_forecast.forecast("Nopur", "Tomato", "All", state="Testland")[0]
    assert e["scope_level"] == "state"
    assert e["district"] is None


def test_stale_days_is_the_true_age_not_the_capped_projection(store):
    """A year-old last month must be reported as a year old."""
    seed(store, months=14)  # ends 2025-02
    e = price_forecast.forecast(None, "Tomato", "All", state="Testland")[0]
    assert e["stale_days"] > price_forecast._MAX_STALE_SHIFT


def test_price_lookup_falls_back_to_the_monthly_average(store, monkeypatch):
    """A state with no daily feed still shows its published average, labelled
    as a monthly average and flagged real."""
    seed(store, months=14)
    monkeypatch.setattr(mandi_prices, "_live_records", lambda *a, **k: [])
    r = mandi_prices.get_price("Tomato", "Testpur", "Testland")
    assert r, "no price despite published monthly averages"
    assert r["source"] == "agmarknet_monthly"
    assert r["is_real"] is True
    assert r["scope"] in ("district", "state")
    assert (r.get("state") or "") == "Testland"
    assert len(r["date"]) == 10  # a month-end date, not a day-rate claim


def test_predictable_picker_needs_real_coverage(store):
    """Only crops with enough history are offered for forecasting."""
    seed(store, months=14)
    seed(store, commodity="Cabbage", months=3)
    usable = store.forecastable_commodities("Testland")
    assert "Tomato" in usable
    assert "Cabbage" not in usable


def test_forecast_never_invents_a_state(store):
    seed(store, months=26)
    assert price_forecast.forecast(None, "Tomato", "All", state="Nowhereland") == []


def test_daily_history_still_wins_when_thicker(store):
    """A state with dense daily rows must keep using them, and say so."""
    rows = []
    start = pd.Timestamp("2025-01-01")
    for i in range(120):
        rows.append({"date": str((start + pd.Timedelta(days=i)).date()),
                     "state": "Testland", "district": "Testpur",
                     "market": "APMC Testpur", "commodity": "Tomato",
                     "variety": "Local", "modal_price": 1800 + i,
                     "source": "agmarknet_live"})
    store.upsert_many(rows)
    seed(store, months=26)
    e = price_forecast.forecast(None, "Tomato", "All", state="Testland")[0]
    assert e["history_basis"] == "daily"
    assert e["history_last"].count("-") == 2  # a date, not a month
