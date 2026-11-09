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

import difflib
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date as date_cls
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from config import settings  # single env entry point

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = settings.price_db_override or os.path.join(_HERE, "mandi_price_store.db")

_COLS = ("date", "state", "district", "market", "commodity", "variety",
         "min_price", "max_price", "modal_price", "source", "fetched_at")

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None

# The UI sends official spellings, AGMARKNET publishes its own. These groups
# are the states/districts where they differ, so a monthly lookup finds the
# rows regardless of which spelling was stored.
_NAME_GROUPS = [
    {"kerala", "keralam"},
    {"chhattisgarh", "chattisgarh", "chatisgarh"},
    {"delhi", "nct of delhi", "new delhi"},
    {"puducherry", "pondicherry"},
    {"uttarakhand", "uttrakhand", "uttaranchal"},
    {"odisha", "orissa"},
    {"andaman and nicobar", "andaman and nicobar islands", "andaman & nicobar islands"},
    {"dadra and nagar haveli", "dadra and nagar haveli and daman and diu",
     "dadra & nagar haveli"},
    {"daman and diu", "dadra and nagar haveli and daman and diu"},
    {"bengaluru", "bangalore", "bengaluru urban", "bangalore urban"},
    {"belagavi", "belgaum"},
    {"mysuru", "mysore"},
    {"mangaluru", "mangalore"},
    {"hubballi", "hubli"},
    {"shivamogga", "shimoga"},
    {"tumakuru", "tumkur"},
    {"kalaburagi", "gulbarga"},
    {"vijayapura", "bijapur"},
    {"ballari", "bellary"},
    {"chikkamagaluru", "chikmagalur"},
    {"davanagere", "davangere"},
    {"vijayanagar", "vijayanagara"},
    {"thrissur", "thirssur", "trissur", "trichur"},
    {"gurugram", "gurgaon"},
    {"prayagraj", "allahabad"},
    {"faizabad", "ayodhya"},
    {"ahilyanagar", "ahmednagar"},
    {"chhatrapati sambhajinagar", "aurangabad"},
    {"dharashiv", "osmanabad"},
    {"mumbai suburban", "mumbai", "mumbai city"},
    {"howrah", "haora"},
    {"hooghly", "hugli"},
    {"kolkata", "calcutta"},
    {"cooch behar", "koch bihar"},
    {"darjeeling", "darjiling"},
    {"purba medinipur", "east midnapore"},
    {"paschim medinipur", "west midnapore"},
]


def _norm_name(name) -> str:
    return " ".join(str(name or "").strip().lower().replace("-", " ").split())


def name_variants(name) -> set:
    """Stored spellings a place name may appear under."""
    key = _norm_name(name)
    if not key:
        return set()
    out = {key}
    for group in _NAME_GROUPS:
        if key in group:
            out |= group
    return out


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
        # Monthly district averages from the AGMARKNET "district-wise wholesale
        # prices monthly analysis" report. These are real published averages, not
        # derived guesses, and they are what make a 2-year series possible for
        # states whose daily history we never captured.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mandi_monthly (
                state       TEXT NOT NULL DEFAULT '',
                district    TEXT NOT NULL DEFAULT '',
                commodity   TEXT NOT NULL DEFAULT '',
                year        INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                price       REAL NOT NULL,
                source      TEXT NOT NULL DEFAULT 'agmarknet_monthly',
                fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(state, district, commodity, year, month)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mm_lookup ON mandi_monthly (commodity, district, year, month)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mm_state ON mandi_monthly (state, commodity, year, month)")


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
           state: Optional[str] = None, max_age_days: int = 120,
           limit: int = 1, allow_any: bool = True,
           district_aliases: Optional[Iterable[str]] = None,
           state_aliases: Optional[Iterable[str]] = None) -> List[sqlite3.Row]:
    """Latest cached rows for a commodity: exact district, then same state,
    then (only while `allow_any`) anything in the country. Only rows within
    max_age_days.

    `district_aliases` / `state_aliases` widen the name match: the store keeps
    the AGMARKNET spelling (Belgaum, Keralam, NCT of Delhi) while the UI sends
    the current official one (Belagavi, Kerala, Delhi).

    `allow_any=False` is what a scoped request needs: a Jharkhand farmer must
    never be shown a Tamil Nadu rate dressed up as their local price.
    """
    init_db()
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    key = (commodity or "").strip().lower()
    dnames = {str(district).strip().lower()} | {
        str(a).strip().lower() for a in (district_aliases or []) if str(a).strip()
    }
    snames = {str(state).strip().lower()} | {
        str(a).strip().lower() for a in (state_aliases or []) if str(a).strip()
    }
    with _lock:
        conn = _connect()
        if district and str(district).lower() not in ("", "all", "none"):
            rows = conn.execute(
                "SELECT * FROM mandi_prices WHERE lower(commodity) = ? "
                f"AND lower(district) IN ({','.join('?' * len(dnames))}) "
                "AND date >= ? AND modal_price > 0 "
                "ORDER BY date DESC LIMIT ?",
                (key, *sorted(dnames), cutoff, limit)).fetchall()
            if rows:
                return rows
        if state:
            rows = conn.execute(
                "SELECT * FROM mandi_prices WHERE lower(commodity) = ? "
                f"AND lower(state) IN ({','.join('?' * len(snames))}) "
                "AND date >= ? AND modal_price > 0 "
                "ORDER BY date DESC LIMIT ?",
                (key, *sorted(snames), cutoff, limit)).fetchall()
            if rows:
                return rows
        if not allow_any:
            return []
        return conn.execute("""
            SELECT * FROM mandi_prices
            WHERE lower(commodity) = ? AND date >= ? AND modal_price > 0
            ORDER BY date DESC LIMIT ?
        """, (key, cutoff, limit)).fetchall()


def prune_live_rows(state: Optional[str], district: str, day: str,
                    keep: set) -> int:
    """Delete name-drifted live rows for one district-day.

    api.data.gov.in's commodity filter is loose: asking for a crop the district
    does not trade returns another crop's row, which the old code then stored
    under the requested name (a Bajra card carrying Ragi's price). A fresh live
    snapshot knows exactly which (market, commodity, variety) triples that
    district actually filed, so anything else stored for that same day is
    wrong and can go. Only `agmarknet_live` rows for the exact day are touched;
    history, backfills and monthly averages are never deleted.
    """
    if not (district and day and keep):
        return 0
    snames = sorted(name_variants(state)) or [str(state or "").strip().lower()]
    dnames = sorted(name_variants(district))
    with _tx() as conn:
        rows = conn.execute(
            "SELECT rowid, market, commodity, variety FROM mandi_prices "
            "WHERE date = ? AND source LIKE 'agmarknet_live%' "
            f"AND lower(state) IN ({','.join('?' * len(snames))}) "
            f"AND lower(district) IN ({','.join('?' * len(dnames))})",
            (day, *snames, *dnames)).fetchall()
        victims = [
            r["rowid"] for r in rows
            if (str(r["market"] or "").strip(),
                str(r["commodity"] or "").strip(),
                str(r["variety"] or "").strip()) not in keep
        ]
        for rowid in victims:
            conn.execute("DELETE FROM mandi_prices WHERE rowid = ?", (rowid,))
    return len(victims)


def history(commodity: str, district: Optional[str] = None,
            state: Optional[str] = None, years: float = 2.0) -> pd.DataFrame:
    """Full daily history (any market in scope) for forecasting."""
    init_db()
    since = (pd.Timestamp.today() - pd.Timedelta(days=int(years * 365.25))) \
        .strftime("%Y-%m-%d")
    with _lock:
        conn = _connect()
        q = ["SELECT date, state, district, market, commodity, min_price, "
             "max_price, modal_price, source FROM mandi_prices "
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


def monthly_upsert_many(rows: Iterable[dict]) -> int:
    """Insert/update monthly district averages.

    Each row: state/district/commodity/year/month/price. Returns rows written.
    """
    init_db()
    n = 0
    with _tx() as conn:
        for r in rows:
            try:
                price = float(r["price"])
                year = int(r["year"])
                month = int(r["month"])
            except (KeyError, TypeError, ValueError):
                continue
            if price <= 0 or price > 1_000_000 or not (1 <= month <= 12):
                continue
            conn.execute("""
                INSERT INTO mandi_monthly
                    (state, district, commodity, year, month, price, source, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(state, district, commodity, year, month)
                DO UPDATE SET price=excluded.price, source=excluded.source,
                              fetched_at=datetime('now')
            """, (str(r.get("state") or ""), str(r.get("district") or ""),
                  str(r.get("commodity") or ""), year, month, price,
                  str(r.get("source") or "agmarknet_monthly")))
            n += 1
    return n


DERIVED_SOURCE = "derived_daily"


def _month_bounds(year: int, month: int) -> tuple:
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    return start, end


def recent_months(count: int = 2) -> List[tuple]:
    """The last `count` (year, month) pairs, newest first."""
    today = date_cls.today()
    y, m = today.year, today.month
    out = []
    for _ in range(max(1, count)):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def monthly_from_daily(min_days: int = 10,
                       months: Optional[List[tuple]] = None) -> int:
    """Monthly district averages computed from our own daily rows.

    From today on the daily feed is the source of truth, so the monthly series
    is derived here instead of re-fetching AGMARKNET's monthly report. Two
    guards keep this honest:

    * a month only produces rows once it has `min_days` distinct observed days
      — a 3-day "monthly average" would be a made-up number;
    * an average already published by AGMARKNET (source `agmarknet_monthly`) is
      never overwritten, so existing history stays exactly as imported.
    """
    init_db()
    months = months or recent_months(2)
    payload = []
    with _tx() as conn:
        for year, month in months:
            start, end = _month_bounds(year, month)
            cur = conn.execute(
                """
                SELECT state, district, commodity,
                       AVG(modal_price) AS price,
                       COUNT(DISTINCT date) AS days
                FROM mandi_prices
                WHERE date >= ? AND date < ? AND modal_price IS NOT NULL AND modal_price > 0
                GROUP BY state, district, commodity
                HAVING COUNT(DISTINCT date) >= ?
                """,
                (start, end, int(min_days)),
            )
            for r in cur.fetchall():
                prev = conn.execute(
                    "SELECT source FROM mandi_monthly WHERE state=? AND district=? "
                    "AND commodity=? AND year=? AND month=?",
                    (r["state"], r["district"], r["commodity"], year, month),
                ).fetchone()
                if prev and prev["source"] != DERIVED_SOURCE:
                    continue        # the published average wins
                payload.append({
                    "state": r["state"], "district": r["district"],
                    "commodity": r["commodity"], "year": year, "month": month,
                    "price": round(float(r["price"]), 2), "source": DERIVED_SOURCE,
                })
    return monthly_upsert_many(payload) if payload else 0


def prune_monthly(keep_months: int = 36, dry_run: bool = False) -> dict:
    """Delete derived monthly rows older than `keep_months`.

    Only rows we produced ourselves are eligible: an imported AGMARKNET average
    can never be recovered from the daily table, so it is never deleted. Off by
    default — the whole store is ~14 MB and the forecast only reads 24 months,
    so trimming buys nothing measurable.
    """
    keep_months = max(24, int(keep_months))
    today = date_cls.today()
    y, m = today.year, today.month - keep_months
    while m <= 0:
        m += 12
        y -= 1
    with _tx() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM mandi_monthly WHERE source=? "
            "AND (year < ? OR (year = ? AND month < ?))",
            (DERIVED_SOURCE, y, y, m),
        ).fetchone()
        victims = int(row[0]) if row else 0
        if victims and not dry_run:
            conn.execute(
                "DELETE FROM mandi_monthly WHERE source=? "
                "AND (year < ? OR (year = ? AND month < ?))",
                (DERIVED_SOURCE, y, y, m),
            )
    return {"cutoff": f"{y}-{m:02d}", "keep_months": keep_months,
            "rows": victims, "deleted": 0 if dry_run else victims}


def monthly_history(commodity: str, district: Optional[str] = None,
                    state: Optional[str] = None) -> pd.DataFrame:
    """Monthly average price series for a commodity in scope.

    Returns `date` (first of month) + `price`, one row per month, averaged over
    markets when the scope is a whole district or state. Empty when the scope
    has no monthly rows.
    """
    init_db()
    where = ["lower(commodity) = ?", "price > 0"]
    args: List[object] = [(commodity or "").strip().lower()]
    if district and str(district).strip().lower() not in ("", "all", "none"):
        dv = sorted(name_variants(district))
        where.append(f"lower(district) IN ({','.join('?' * len(dv))})")
        args.extend(dv)
    if state and str(state).strip().lower() not in ("", "all", "none"):
        sv = sorted(name_variants(state))
        where.append(f"lower(state) IN ({','.join('?' * len(sv))})")
        args.extend(sv)
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT year, month, AVG(price) AS price FROM mandi_monthly WHERE "
            + " AND ".join(where) + " GROUP BY year, month ORDER BY year, month",
            args).fetchall()
    if not rows:
        return pd.DataFrame(columns=["date", "price"])
    return pd.DataFrame([
        {"date": pd.Timestamp(year=int(r["year"]), month=int(r["month"]), day=1),
         "price": float(r["price"])}
        for r in rows
    ])


def monthly_months_present(state: str, commodity: str) -> set:
    """(year, month) pairs already stored for a state+commodity.

    Lets a backfill resume instead of refetching months it already has.
    """
    init_db()
    sv = sorted(name_variants(state)) or [""]
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT year, month FROM mandi_monthly "
            f"WHERE lower(state) IN ({','.join('?' * len(sv))}) "
            "AND lower(commodity) = ?",
            (*sv, str(commodity or "").strip().lower())
        ).fetchall()
    return {(int(r["year"]), int(r["month"])) for r in rows}


def monthly_coverage() -> dict:
    init_db()
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT state) st, COUNT(DISTINCT district) d, "
            "COUNT(DISTINCT commodity) c, MIN(year*12+month-1) a, MAX(year*12+month-1) b "
            "FROM mandi_monthly").fetchone()
    return {
        "rows": row["n"], "states": row["st"], "districts": row["d"],
        "commodities": row["c"],
        "first_month": _ym_label(row["a"]), "last_month": _ym_label(row["b"]),
    }


def _ym_label(v) -> Optional[str]:
    """Encode/decode `year*12 + month - 1` so December keeps its own year."""
    if v is None:
        return None
    v = int(v)
    return f"{v // 12:04d}-{v % 12 + 1:02d}"


def daily_market_counts(days: Iterable[str]) -> dict:
    """
    Distinct markets that reported *any* commodity on each given date.

    Used as the ingest baseline: a day where the whole feed carried fewer
    markets must not be read as one commodity's supply collapsing.
    """
    days = [str(d) for d in days if d]
    if not days:
        return {}
    init_db()
    marks = ",".join("?" * len(days))
    with _lock:
        conn = _connect()
        rows = conn.execute(
            f"SELECT date, COUNT(DISTINCT market) n FROM mandi_prices "
            f"WHERE date IN ({marks}) GROUP BY date", days).fetchall()
    return {r["date"]: int(r["n"]) for r in rows}


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


_DISTRICT_SPELLINGS: Dict[str, Any] = {"at": 0.0, "names": []}
_DISTRICT_SPELLING_TTL = 600


def _squash(name: str) -> str:
    """Letters only, so "Dr. B.R. Ambedkar" and "Dr BRAmbedkar" compare."""
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _stored_district_names() -> List[str]:
    """Every district spelling the store holds (rebuilt every few minutes)."""
    now = pd.Timestamp.now().timestamp()
    if _DISTRICT_SPELLINGS["names"] and \
            now - _DISTRICT_SPELLINGS["at"] < _DISTRICT_SPELLING_TTL:
        return _DISTRICT_SPELLINGS["names"]
    init_db()
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT district FROM mandi_prices WHERE district != '' "
            "UNION SELECT district FROM mandi_monthly WHERE district != ''"
        ).fetchall()
    names = sorted({str(r["district"]).strip() for r in rows if r["district"]})
    _DISTRICT_SPELLINGS.update(at=now, names=names)
    return names


def resolve_district(name: Optional[str]) -> Optional[str]:
    """The spelling this store actually files a district under.

    The app ships the current official name ("Davanagere") while AGMARKNET and
    the price store still write the older one ("Davangere", "Vijayanagara").
    Looking a district up under the wrong spelling returned no daily rows and
    no mandis at all, so its page fell back to the state's crops. An exact or
    "spelling-variant" match wins; otherwise a near-identical spelling (one or
    two letters apart) is accepted, and only when it is clearly the closest
    match — "Warangal Rural" must not silently become "Warangal".
    """
    if not name:
        return None
    key = _norm_name(name)
    if not key:
        return None
    variants = sorted(name_variants(name) | {key})
    placeholders = ",".join("?" * len(variants))
    init_db()
    with _lock:
        conn = _connect()
        for table in ("mandi_prices", "mandi_monthly"):
            row = conn.execute(
                f"SELECT district, COUNT(*) n FROM {table} "
                f"WHERE lower(district) IN ({placeholders}) AND district != '' "
                f"GROUP BY district ORDER BY n DESC LIMIT 1",
                tuple(variants)).fetchone()
            if row and row["district"]:
                return row["district"]

    # Spelling drift (Kanyakumari/Kanniyakumari, Chittoor/Chittor,
    # Chamarajanagar/Chamarajanagara). A unique, near-identical candidate is
    # the same district; anything ambiguous is left unresolved so the caller
    # says "no data" instead of borrowing a neighbour's crops.
    target = _squash(name)
    if not target:
        return None
    scored = []
    for cand in _stored_district_names():
        other = _squash(cand)
        if not other or abs(len(other) - len(target)) > 4:
            continue
        score = difflib.SequenceMatcher(None, target, other).ratio()
        if score >= 0.9:
            scored.append((score, cand))
    if not scored:
        return None
    scored.sort(reverse=True)
    best, second = scored[0], scored[1] if len(scored) > 1 else (0.0, None)
    if best[0] >= 0.9 and best[0] - second[0] >= 0.03:
        return best[1]
    return None


def state_for_district(district: Optional[str]) -> Optional[str]:
    """Most common state for a district in the store (or None).

    Daily rows win, then the monthly averages — a district that only exists in
    the AGMARKNET monthly backfill still resolves to its state, which is what
    lets the forecast fall back to a state-level series instead of India.
    """
    if not district:
        return None
    init_db()
    key = str(district).strip().lower()
    with _lock:
        conn = _connect()
        row = conn.execute("""
            SELECT state, COUNT(*) n FROM mandi_prices
            WHERE lower(district) = ? AND state != ''
            GROUP BY state ORDER BY n DESC LIMIT 1
        """, (key,)).fetchone()
        if row:
            return row["state"]
        dv = sorted(name_variants(district))
        row = conn.execute("""
            SELECT state, COUNT(*) n FROM mandi_monthly
            WHERE lower(district) IN (""" + ",".join("?" * len(dv)) + """) AND state != ''
            GROUP BY state ORDER BY n DESC LIMIT 1
        """, tuple(dv)).fetchone()
    return row["state"] if row else None


def has_state(state: str) -> bool:
    """True when the store holds any real price row for this state."""
    if not state or str(state).strip().lower() in ("", "all", "none"):
        return False
    init_db()
    key = str(state).strip().lower()
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT 1 FROM mandi_prices WHERE lower(state) = ? LIMIT 1", (key,)     
        ).fetchone()
        if row:
            return True
        sv = sorted(name_variants(state))
        row = conn.execute(
            "SELECT 1 FROM mandi_monthly WHERE lower(state) IN ("
            + ",".join("?" * len(sv)) + ") LIMIT 1", tuple(sv)
        ).fetchone()
    return row is not None


def monthly_commodities(state: Optional[str] = None,
                        district: Optional[str] = None) -> List[str]:
    """Commodities that have at least one published monthly average."""
    init_db()
    where = ["price > 0"]
    args: List[object] = []
    if district and str(district).strip().lower() not in ("", "all", "none"):
        dv = sorted(name_variants(district))
        where.append(f"lower(district) IN ({','.join('?' * len(dv))})")
        args.extend(dv)
    if state and str(state).strip().lower() not in ("", "all", "none"):
        sv = sorted(name_variants(state))
        where.append(f"lower(state) IN ({','.join('?' * len(sv))})")
        args.extend(sv)
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT commodity FROM mandi_monthly WHERE "
            + " AND ".join(where) + " ORDER BY commodity", args).fetchall()
    return [r["commodity"] for r in rows if r["commodity"]]


def forecastable_commodities(state: Optional[str] = None,
                             district: Optional[str] = None,
                             min_monthly: int = 12,
                             min_daily: int = 60) -> List[str]:
    """Crops the forecast can actually run for in this scope.

    A commodity qualifies when it has enough daily observations (>=60) or at
    least `min_monthly` published monthly averages — the same thresholds the
    model uses. The picker offers only these, so nobody selects a crop and
    lands on "not enough history".
    """
    init_db()
    d = str(district or "").strip().lower() if str(district or "").strip().lower() not in (
        "", "all", "none") else ""
    s = str(state or "").strip().lower() if str(state or "").strip().lower() not in (
        "", "all", "none") else ""

    out: set = set()
    with _lock:
        conn = _connect()
        for table, group_col, need in (("mandi_monthly", "commodity", min_monthly),
                                       ("mandi_prices", "commodity", min_daily)):
            where = ["1=1"]
            args: List[object] = []
            if table == "mandi_prices":
                where.append("modal_price > 0")
            if d:
                dv = sorted(name_variants(d))
                where.append(f"lower(district) IN ({','.join('?' * len(dv))})")
                args.extend(dv)
            if s:
                sv = sorted(name_variants(s))
                where.append(f"lower(state) IN ({','.join('?' * len(sv))})")
                args.extend(sv)
            keys = ("year * 12 + month" if table == "mandi_monthly" else "date")
            rows = conn.execute(
                f"SELECT {group_col} c FROM {table} WHERE " + " AND ".join(where)
                + f" GROUP BY {group_col} HAVING COUNT(DISTINCT {keys}) >= ?",
                (*args, need)).fetchall()
            out |= {r["c"] for r in rows if r["c"]}
    return sorted(out)


def monthly_state_summary(limit: int = 40) -> List[dict]:
    """Per state+commodity span of the monthly backfill, longest first."""
    init_db()
    with _lock:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT state, commodity, COUNT(DISTINCT year * 12 + month) months,
                   COUNT(DISTINCT district) districts,
                   MIN(year * 12 + month - 1) a, MAX(year * 12 + month - 1) b
            FROM mandi_monthly GROUP BY state, commodity
            ORDER BY months DESC, state LIMIT ?
            """, (max(1, min(int(limit), 500)),)).fetchall()
    return [{"state": r["state"], "commodity": r["commodity"],
             "months": int(r["months"]), "districts": int(r["districts"]),
             "first_month": _ym_label(r["a"]), "last_month": _ym_label(r["b"])}
            for r in rows]


def distinct_commodities(district: Optional[str] = None,
                         state: Optional[str] = None,
                         allow_any: bool = True,
                         district_aliases: Optional[Iterable[str]] = None,
                         state_aliases: Optional[Iterable[str]] = None,
                         max_age_days: Optional[int] = None) -> List[str]:
    """Commodities that have a real row, optionally limited to a scope.

    With a district or state the list is what that market actually reported —
    not the national catalogue. `allow_any=False` stops an unscoped call from
    returning everything, so a scoped request can never widen on its own.

    `max_age_days` optionally limits the list to recently traded crops; the
    default keeps every real row, because a state whose only record is a
    published monthly average still trades that crop.

    Daily rows and the AGMARKNET monthly averages are unioned: a state that
    exists only in the monthly backfill still lists its crops.
    """
    init_db()
    d = str(district or "").strip().lower()
    s = str(state or "").strip().lower()
    scoped_district = d not in ("", "all", "none")
    scoped_state = s not in ("", "all", "none")
    if not allow_any and not scoped_district and not scoped_state:
        return []

    where: List[str] = ["modal_price > 0"]
    args: List[object] = []
    cutoff = None
    if max_age_days and (scoped_district or scoped_state):
        cutoff = (pd.Timestamp.today()
                  - pd.Timedelta(days=int(max_age_days))).strftime("%Y-%m-%d")
        where.append("date >= ?")
        args.append(cutoff)
    if scoped_district:
        dnames = {d} | {str(a).strip().lower() for a in (district_aliases or [])
                        if str(a).strip()}
        where.append(f"lower(district) IN ({','.join('?' * len(dnames))})")
        args.extend(sorted(dnames))
    if scoped_state:
        snames = {s} | {str(a).strip().lower() for a in (state_aliases or [])
                        if str(a).strip()}
        where.append(f"lower(state) IN ({','.join('?' * len(snames))})")
        args.extend(sorted(snames))

    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT commodity FROM mandi_prices WHERE "
            + " AND ".join(where) + " ORDER BY commodity", args).fetchall()
    names = {r["commodity"] for r in rows if r["commodity"]}

    # Monthly published averages cover states the daily feed never captured,
    # so a state page lists the crops it actually trades even without daily
    # rows.
    mwhere: List[str] = ["price > 0"]
    margs: List[object] = []
    if cutoff:
        # Same freshness window as the daily rows, in (year, month) terms.
        cy, cm = int(cutoff[:4]), int(cutoff[5:7])
        mwhere.append("year * 100 + month >= ?")
        margs.append(cy * 100 + cm)
    if scoped_district:
        dnames_m = {d} | {str(a).strip().lower() for a in (district_aliases or [])
                          if str(a).strip()} | name_variants(d)
        mwhere.append(f"lower(district) IN ({','.join('?' * len(dnames_m))})")
        margs.extend(sorted(dnames_m))
    if scoped_state:
        snames_m = {s} | {str(a).strip().lower() for a in (state_aliases or [])
                          if str(a).strip()} | name_variants(s)
        mwhere.append(f"lower(state) IN ({','.join('?' * len(snames_m))})")
        margs.extend(sorted(snames_m))
    with _lock:
        conn = _connect()
        mrows = conn.execute(
            "SELECT DISTINCT commodity FROM mandi_monthly WHERE "
            + " AND ".join(mwhere), margs).fetchall()
    names |= {r["commodity"] for r in mrows if r["commodity"]}
    return sorted(names)


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
