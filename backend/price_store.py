"""
Local price history store for FarmIntel (Phase 1).

SQLite keeps the accumulating REAL mandi history that the backend serves
when the live AGMARKNET API is slow or unavailable. Every row comes from a
real source (live AGMARKNET fetch or the Goa historical parquet import) —
the store never synthesizes numbers.

Schema mirrors the Supabase `mandi_prices` table (see supabase/migrations)
so rows can be pushed to Supabase without transformation:

  date TEXT, state TEXT, district TEXT, market TEXT, commodity TEXT,
  variety TEXT, min_price REAL, max_price REAL, modal_price REAL,
  source TEXT, fetched_at TEXT
  UNIQUE(date, state, district, market, commodity, variety)
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date as date_cls
from typing import Iterable, List, Optional

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FARMINTEL_PRICE_DB",
                         os.path.join(_HERE, "mandi_price_store.db"))

_COLS = ("date", "state", "district", "market", "commodity", "variety",
         "min_price", "max_price", "modal_price", "source", "fetched_at")

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                                isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


@contextmanager
def _tx():
    with _lock:
        conn = _connect()
        try:
            yield conn
        except Exception:
            raise


def init_db() -> None:
    with _tx() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mandi_prices (
                date        TEXT NOT NULL,
                state       TEXT NOT NULL DEFAULT '',
                district    TEXT NOT NULL DEFAULT '',
                market      TEXT NOT NULL DEFAULT '',
                commodity   TEXT NOT NULL DEFAULT '',
                variety     TEXT NOT NULL DEFAULT '',
                min_price   REAL,
                max_price   REAL,
                modal_price REAL NOT NULL,
                source      TEXT NOT NULL DEFAULT 'agmarknet_live',
                fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(date, state, district, market, commodity, variety)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mp_lookup ON mandi_prices (commodity, district, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mp_state ON mandi_prices (state, commodity, date)")


def upsert_many(rows: Iterable[dict]) -> int:
    """Insert/update price rows. Each row: date/state/district/market/
    commodity/variety/min_price/max_price/modal_price/source. Returns count."""
    init_db()
    n = 0
    with _tx() as conn:
        for r in rows:
            if r.get("modal_price") in (None, ""):
                continue
            try:
                modal = float(r["modal_price"])
            except (TypeError, ValueError):
                continue
            if modal <= 0 or modal > 1_000_000:
                continue
            conn.execute("""
                INSERT INTO mandi_prices
                    (date, state, district, market, commodity, variety,
                     min_price, max_price, modal_price, source, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(date, state, district, market, commodity, variety)
                DO UPDATE SET min_price=excluded.min_price,
                              max_price=excluded.max_price,
                              modal_price=excluded.modal_price,
                              source=excluded.source,
                              fetched_at=datetime('now')
            """, (
                str(r.get("date", "")),
                str(r.get("state") or ""),
                str(r.get("district") or ""),
                str(r.get("market") or ""),
                str(r.get("commodity") or ""),
                str(r.get("variety") or ""),
                _f(r.get("min_price")), _f(r.get("max_price")), modal,
                str(r.get("source") or "agmarknet_live"),
            ))
            n += 1
    return n


def _f(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def lookup(commodity: str, district: Optional[str] = None,
           state: Optional[str] = None, max_age_days: int = 45,
           limit: int = 1) -> List[sqlite3.Row]:
    """Latest cached rows for a commodity (prefer exact district, then
    same-state rows, then anything). Only rows within max_age_days."""
    init_db()
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    key = (commodity or "").strip().lower()
    with _lock:
        conn = _connect()
        if district and str(district).lower() not in ("", "all", "none"):
            rows = conn.execute("""
                SELECT * FROM mandi_prices
                WHERE lower(commodity) = ? AND lower(district) = ?
                  AND date >= ? AND modal_price > 0
                ORDER BY date DESC LIMIT ?
            """, (key, str(district).strip().lower(), cutoff, limit)).fetchall()
            if rows:
                return rows
        if state:
            rows = conn.execute("""
                SELECT * FROM mandi_prices
                WHERE lower(commodity) = ? AND lower(state) = ?
                  AND date >= ? AND modal_price > 0
                ORDER BY date DESC LIMIT ?
            """, (key, str(state).strip().lower(), cutoff, limit)).fetchall()
            if rows:
                return rows
        return conn.execute("""
            SELECT * FROM mandi_prices
            WHERE lower(commodity) = ? AND date >= ? AND modal_price > 0
            ORDER BY date DESC LIMIT ?
        """, (key, cutoff, limit)).fetchall()


def history(commodity: str, district: Optional[str] = None,
            state: Optional[str] = None, years: float = 2.0) -> pd.DataFrame:
    """Full daily history (any market in scope) for forecasting."""
    init_db()
    since = (pd.Timestamp.today() - pd.Timedelta(days=int(years * 365.25))) \
        .strftime("%Y-%m-%d")
    with _lock:
        conn = _connect()
        q = ["SELECT date, state, district, market, commodity, min_price, "
             "max_price, modal_price FROM mandi_prices "
             "WHERE lower(commodity) = ? AND date >= ? AND modal_price > 0"]
        args = [(commodity or "").strip().lower(), since]
        if district:
            q.append("AND lower(district) = ?")
            args.append(str(district).strip().lower())
        if state:
            q.append("AND lower(state) = ?")
            args.append(str(state).strip().lower())
        df = pd.read_sql(" ".join(q), conn, params=args)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def coverage() -> dict:
    """Real data coverage summary for the status endpoint / final report."""
    init_db()
    with _lock:
        conn = _connect()
        today = date_cls.today().strftime("%Y-%m-%d")
        total = conn.execute("SELECT COUNT(*) c, MIN(date) first, MAX(date) last "
                             "FROM mandi_prices").fetchone()
        by_source = conn.execute(
            "SELECT source, COUNT(*) n FROM mandi_prices GROUP BY source").fetchall()
        week_ago = (pd.Timestamp.today() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        stale = conn.execute(
            "SELECT COUNT(*) c FROM mandi_prices WHERE date < ?",
            (week_ago,),
        ).fetchone()
    return {
        "db": DB_PATH,
        "rows": total["c"],
        "first_date": total["first"],
        "last_date": total["last"],
        "fresh_rows_last_7d": (total["c"] or 0) - (stale["c"] or 0),
        "by_source": {r["source"]: r["n"] for r in by_source},
    }


def state_for_district(district: Optional[str]) -> Optional[str]:
    """Most common state for a district in the store (or None)."""
    if not district:
        return None
    init_db()
    with _lock:
        conn = _connect()
        row = conn.execute("""
            SELECT state, COUNT(*) n FROM mandi_prices
            WHERE lower(district) = ? AND state != ''
            GROUP BY state ORDER BY n DESC LIMIT 1
        """, (str(district).strip().lower(),)).fetchone()
    return row["state"] if row else None


def distinct_commodities() -> List[str]:
    init_db()
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT commodity FROM mandi_prices ORDER BY commodity"
        ).fetchall()
    return [r["commodity"] for r in rows if r["commodity"]]


def distinct_markets() -> List[dict]:
    init_db()
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT district, market FROM mandi_prices "
            "ORDER BY district, market"
        ).fetchall()
    return [{"district": r["district"], "market": r["market"]}
            for r in rows if r["market"]]
