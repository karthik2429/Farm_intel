"""
Phase 1 guard tests: the price pipeline must serve REAL data or nothing.

Fails if:
  - mandi_prices.get_price ever returns a synthetic/fabricated source
  - a returned price lies about its provenance (is_real / badge)
  - price_forecast returns an unusable forecast for a series that has real
    history (inverted CI, wrong dates)
  - the store silently loses the real Goa backfill + live coverage

Run from the repo root:
    ./collab/venv/bin/python -m pytest Farm_intel/backend/tests -q
"""

import os
import sys
from pathlib import Path

import pandas as pd

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# NOTE: importing mandi_ingest first loads Farm_intel/.env (test env too)
import mandi_ingest  # noqa: E402
import mandi_prices  # noqa: E402
import price_store  # noqa: E402
import price_forecast  # noqa: E402

# Sources that mean "made up" — must never be served
FORBIDDEN_SOURCES = {
    "snapshot", "district_snapshot", "synthetic", "generated",
    "mandi_price_history.csv",
}


@pytest.fixture(scope="module")
def coverage():
    return price_store.coverage()


# ---------------------------------------------------------------------------
# Store level
# ---------------------------------------------------------------------------

def test_store_has_real_backfill(coverage):
    assert coverage["rows"] > 0
    assert coverage["by_source"].get("agmarknet_backfill", 0) > 0, \
        "real Goa backfill missing from the store"
    first = coverage["first_date"]
    assert first <= "2024-12-31", f"history doesn't reach 2024: {first}"


def test_store_rows_all_have_known_source(coverage):
    with price_store._connect() as conn:
        bad = conn.execute(
            "SELECT COUNT(*) FROM mandi_prices "
            f"WHERE source IN ({','.join('?' * len(FORBIDDEN_SOURCES))})",
            tuple(sorted(FORBIDDEN_SOURCES)),
        ).fetchone()[0]
    assert bad == 0, f"{bad} synthetic-sourced rows found in the store"


# ---------------------------------------------------------------------------
# mandi_prices.get_price — served prices must be real or clearly labelled
# ---------------------------------------------------------------------------

def _assert_real_or_labelled(result, label):
    if not result or result.get("price") is None:
        return  # "not available" is honest: nothing fabricated
    src = result.get("source", "")
    assert src not in FORBIDDEN_SOURCES, \
        f"{label}: synthetic source '{src}' served as a price"
    if src == "msp_reference":
        # real government announcement, but not a market transaction
        assert result.get("is_real") is False, \
            "MSP reference must be flagged is_real=False"
    else:
        assert result.get("is_real") is not False, \
            f"{label}: price flagged is_real=False but served as data"


def test_get_price_guntur_cotton_is_real(monkeypatch):
    """Today's live/backfilled AGMARKNET row must be served as real data."""
    monkeypatch.setattr(mandi_prices, "_LIVE_TIMEOUT", 0.4)  # keep CI fast
    r = mandi_prices.get_price("Cotton", "Guntur", "Andhra Pradesh")
    _assert_real_or_labelled(r, "Guntur/Cotton")
    if r and r.get("price") is not None:
        assert r["source"].startswith(("cache", "agmarknet_live"))


def test_get_price_msp_only_is_labelled(monkeypatch):
    """When only the government MSP reference is available, the response
    must say msp_reference + is_real=False — never pretend it's market data."""
    monkeypatch.setattr(mandi_prices, "_LIVE_TIMEOUT", 0.4)
    r = mandi_prices.get_price("Tur (Arhar/Toor Dal)", "North Goa", "Goa")
    _assert_real_or_labelled(r, "Tur/North Goa")
    if r and r.get("price") is not None:
        if r["source"] == "msp_reference":
            assert r.get("is_real") is False


def test_unavailable_means_price_is_null(monkeypatch):
    """With live probing disabled and no store row, only MSP or null may be
    served — a null price with a fabricated number would be the old bug."""
    monkeypatch.setattr(mandi_prices, "_LIVE_TIMEOUT", 0.3)
    r = mandi_prices.get_price("Sago", "Nowhere District", None)
    if r and r.get("price") is not None:
        assert r["source"] == "msp_reference"


# ---------------------------------------------------------------------------
# Scope: a district/state request must never borrow another state's market
# ---------------------------------------------------------------------------

def _no_live(monkeypatch):
    """Keep the scope tests off the network and independent of API uptime."""
    monkeypatch.setattr(mandi_prices, "_live_records", lambda *a, **k: [])


def test_scoped_request_never_returns_another_state(monkeypatch):
    """A Ranchi request must answer 'nothing', a labelled MSP, or a real
    Jharkhand price — never a row from, say, Tamil Nadu. The AGMARKNET
    monthly average is allowed because it is also Jharkhand's own price."""
    _no_live(monkeypatch)
    r = mandi_prices.get_price("Tomato", "Ranchi", "Jharkhand")
    if r is None:
        return
    if r["source"] == "msp_reference":
        assert r.get("is_real") is False
        return
    assert (r.get("state") or "").lower() == "jharkhand", \
        f"scoped request served {r.get('source')} from {r.get('state')}"
    assert r.get("scope") in ("district", "state")


def test_scoped_price_stays_inside_the_state(monkeypatch):
    _no_live(monkeypatch)
    r = mandi_prices.get_price("Tomato", "Guntur", "Andhra Pradesh")
    if r and r["source"] != "msp_reference":
        assert (r.get("state") or "").lower() == "andhra pradesh"
        assert r.get("scope") in ("district", "state")


def test_unscoped_request_is_labelled_india(monkeypatch):
    """All India is the only scope allowed to serve the national series."""
    _no_live(monkeypatch)
    r = mandi_prices.get_price("Tomato", None, None)
    if r and r["source"] != "msp_reference":
        assert r.get("scope") == "india"


def test_store_lookup_can_refuse_the_national_fallback():
    assert price_store.lookup("Tomato", "Ranchi", "Jharkhand",
                               allow_any=False) == []


# ---------------------------------------------------------------------------
# price_forecast — trajectories must be usable statistics
# ---------------------------------------------------------------------------

def _rich_series_case():
    conns = price_store._connect()
    row = conns.execute(
        "SELECT district, commodity FROM mandi_prices "
        "WHERE state='Goa' GROUP BY district, commodity "
        "HAVING COUNT(*) > 200 ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def test_forecast_trajectory_statistics():
    case = _rich_series_case()
    assert case, "no rich Goa series in the store — backfill import broken"
    out = price_forecast.forecast(district=case["district"],
                                  commodity=case["commodity"])
    assert out, "forecast returned nothing despite 200+ observations"
    e = out[0]
    traj = e["trajectory"]
    assert len(traj) == 14
    prices = [t["predicted_price"] for t in traj]
    assert all(p >= 0 for p in prices)
    for t in traj:  # CI ordering sanity
        assert t["ci_low"] <= t["predicted_price"] <= t["ci_high"]
    # predictions must not drift to absurd proportions of the current price
    cur = e["current_price"]
    worst = max(rid("ci_high", t) - rid("ci_low", t) for t in traj)
    assert worst <= 0.8 * max(cur, 1), \
        f"CI band wider than 80% of the current price ({worst} vs {cur})"


def rid(field, t):
    return t[field]


def test_forecast_reports_staleness():
    case = _rich_series_case()
    out = price_forecast.forecast(district=case["district"],
                                  commodity=case["commodity"])[0]
    assert "stale_days" in out
    assert out["stale_days"] >= 0
    # history never claims it runs into the future
    assert out["history_last"] <= str(pd.Timestamp.today().date())


def test_forecast_unknown_commodity_is_empty_not_synthetic():
    out = price_forecast.forecast(district="Nowhere District",
                                  commodity="Qyxyz")
    assert out == [], "fabricated a forecast without real history"


# ---------------------------------------------------------------------------
# Ingest: no key -> no crash, clear skip
# ---------------------------------------------------------------------------

def test_ingest_without_key_skips_cleanly(monkeypatch):
    monkeypatch.setattr(mandi_ingest, "API_KEY", "")
    n = mandi_ingest.ingest_live_once()
    assert n == 0
