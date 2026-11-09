"""
Monthly averages derived from the daily feed.

From now on the daily rows are the source of truth, so the monthly series is
computed from them rather than re-scraped. These tests pin the two properties
that keep that honest: a month needs enough observed days, and a real published
AGMARKNET average is never replaced.

Run from the repo root:
    python -m pytest Farm_intel/backend/tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import price_store  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A throwaway price store so tests never touch the real one."""
    monkeypatch.setattr(price_store, "DB_PATH", str(tmp_path / "price.db"))
    monkeypatch.setattr(price_store, "_conn", None)
    price_store.init_db()
    yield price_store
    if price_store._conn is not None:
        price_store._conn.close()
    monkeypatch.setattr(price_store, "_conn", None)


def _day(store, day: str, price: float, state="Karnataka", district="Kolar",
         commodity="Tomato") -> None:
    with store._tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mandi_prices "
            "(date, state, district, market, commodity, variety, min_price, max_price,"
            " modal_price, source) VALUES (?,?,?,?,?,'',?,?,?,'test')",
            (day, state, district, "Kolar APMC", commodity, price - 100, price + 100, price),
        )


def _monthly(store, year=2026, month=10):
    return store._connect().execute(
        "SELECT state, district, commodity, price, source FROM mandi_monthly "
        "WHERE year=? AND month=?", (year, month)).fetchall()


def test_derives_the_average_once_enough_days_are_observed(store):
    for i, price in enumerate([1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900], start=1):
        _day(store, f"2026-10-{i:02d}", price)

    written = store.monthly_from_daily(min_days=10, months=[(2026, 10)])

    assert written == 1
    row = _monthly(store)[0]
    assert row["price"] == pytest.approx(1450.0)
    assert row["source"] == price_store.DERIVED_SOURCE


def test_a_thin_month_is_not_turned_into_an_average(store):
    """Nine observed days is not a month — better to store nothing."""
    for i in range(1, 10):
        _day(store, f"2026-10-{i:02d}", 1000 + i)

    assert store.monthly_from_daily(min_days=10, months=[(2026, 10)]) == 0
    assert _monthly(store) == []


def test_published_agmarknet_average_is_never_overwritten(store):
    for i in range(1, 12):
        _day(store, f"2026-10-{i:02d}", 1000)
    store.monthly_upsert_many([{
        "state": "Karnataka", "district": "Kolar", "commodity": "Tomato",
        "year": 2026, "month": 10, "price": 4242.0, "source": "agmarknet_monthly",
    }])

    assert store.monthly_from_daily(min_days=10, months=[(2026, 10)]) == 0
    row = _monthly(store)[0]
    assert row["price"] == pytest.approx(4242.0)
    assert row["source"] == "agmarknet_monthly"


def test_a_rederived_month_is_refreshed(store):
    for i in range(1, 11):
        _day(store, f"2026-10-{i:02d}", 1000)
    store.monthly_from_daily(min_days=10, months=[(2026, 10)])
    _day(store, "2026-10-20", 3000)          # a new observed day arrives

    assert store.monthly_from_daily(min_days=10, months=[(2026, 10)]) == 1
    # averages are stored rounded to paise
    assert _monthly(store)[0]["price"] == pytest.approx((10 * 1000 + 3000) / 11, abs=0.01)


def test_daily_scopes_are_kept_apart(store):
    for i in range(1, 11):
        _day(store, f"2026-10-{i:02d}", 1000, district="Kolar")
        _day(store, f"2026-10-{i:02d}", 2000, district="Mysuru")

    assert store.monthly_from_daily(min_days=10, months=[(2026, 10)]) == 2
    prices = {r["district"]: r["price"] for r in _monthly(store)}
    assert prices == {"Kolar": pytest.approx(1000.0), "Mysuru": pytest.approx(2000.0)}


def test_prune_removes_only_derived_rows(store):
    store.monthly_upsert_many([
        {"state": "Karnataka", "district": "Kolar", "commodity": "Tomato",
         "year": 2019, "month": 3, "price": 800.0, "source": price_store.DERIVED_SOURCE},
        {"state": "Karnataka", "district": "Kolar", "commodity": "Onion",
         "year": 2019, "month": 3, "price": 900.0, "source": "agmarknet_monthly"},
    ])

    dry = store.prune_monthly(keep_months=24, dry_run=True)
    assert dry["rows"] == 1 and dry["deleted"] == 0
    assert len(store._connect().execute("SELECT * FROM mandi_monthly").fetchall()) == 2

    done = store.prune_monthly(keep_months=24)
    assert done["deleted"] == 1
    remaining = store._connect().execute(
        "SELECT commodity, source FROM mandi_monthly").fetchall()
    assert [(r["commodity"], r["source"]) for r in remaining] == [
        ("Onion", "agmarknet_monthly")
    ]
