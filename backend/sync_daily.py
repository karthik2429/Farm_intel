"""
Keep the price store — and its Supabase mirror — current, in one command.

    python sync_daily.py                 # today's prices + derived monthly + push
    python sync_daily.py --push-only     # only mirror what is already local
    python sync_daily.py --portal-monthly  # also re-fetch AGMARKNET's monthly report
    python sync_daily.py --prune-keep-months 36   # trim old derived months

Order matters and is deliberate:

1. Fetch today's AGMARKNET snapshot into SQLite. Idempotent — the resource
   serves the last few days, so a missed run self-heals on the next one.
2. Derive the current and previous month's district averages from those daily
   rows. No extra requests: once a month has ten or more observed days, its
   average is computed here. A month that already holds AGMARKNET's published
   average is left untouched, so imported history never gets rewritten.
   `--portal-monthly` still available for backfilling months we have no daily
   coverage for; it is not part of the daily run because AGMARKNET revises the
   monthly report roughly once a month and each sweep is a few hundred requests.
3. Push the newest daily rows and any freshly derived monthly rows to
   Supabase, upserting on each table's unique key.

Nothing is invented: every number written here came from AGMARKNET. A failed
step is reported and the run continues, so a throttled monthly refresh never
blocks the daily price update.

Exit code is 0 only when every step it attempted succeeded.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple

import requests

import daily_ingest
import price_store
from config import settings

MAJOR_CROPS_HINT = "only state/crop pairs already present locally are refreshed"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(price_store.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- #
# Supabase mirror
# --------------------------------------------------------------------------- #
def _supabase_headers() -> Optional[dict]:
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_key
    if not url or not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _post_batches(endpoint: str, headers: dict, rows: Sequence[dict],
                  batch: int = 500) -> Tuple[int, List[str]]:
    sent = 0
    errors: List[str] = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        for attempt in range(3):
            try:
                resp = requests.post(endpoint, headers=headers, json=chunk, timeout=90)
                if resp.status_code < 300:
                    sent += len(chunk)
                    break
                errors.append(f"HTTP {resp.status_code}: {resp.text[:160]}")
                time.sleep(2 * (attempt + 1))
            except requests.RequestException as exc:
                errors.append(f"{type(exc).__name__}")
                time.sleep(2 * (attempt + 1))
        else:
            errors.append(f"batch at offset {i} failed after 3 attempts")
    return sent, errors


def _iso(ts: Optional[str]) -> Optional[str]:
    """SQLite 'YYYY-MM-DD HH:MM:SS' (IST machine) -> timestamptz string."""
    t = (ts or "").replace(" ", "T")
    if not t:
        return None
    return t if "+" in t else f"{t}+05:30"


def push_daily(days: int = 3) -> Tuple[int, List[str]]:
    """Mirror the newest daily rows. Same window the nightly CI job uses."""
    return daily_ingest.supabase_mirror(limit_days=days), []


def push_monthly(since_days: Optional[int] = 3, everything: bool = False) -> Tuple[int, List[str]]:
    """Mirror monthly averages.

    `since_days` keeps a daily run to the handful of rows that were refreshed
    today; `everything=True` re-pushes the whole table (still idempotent).
    """
    headers = _supabase_headers()
    if headers is None:
        return 0, ["SUPABASE_URL / SUPABASE_SERVICE_KEY not set"]
    where = "" if everything else f"WHERE fetched_at >= datetime('now', '-{int(since_days)} days')"
    rows = _db().execute(
        "SELECT state, district, commodity, year, month, price, source, fetched_at "
        f"FROM mandi_monthly {where} ORDER BY state, commodity, year, month"
    ).fetchall()
    if not rows:
        return 0, []
    payload = [{
        "state": r["state"], "district": r["district"], "commodity": r["commodity"],
        "year": r["year"], "month": r["month"], "price": r["price"],
        "source": r["source"], "fetched_at": _iso(r["fetched_at"]),
    } for r in rows]
    endpoint = (f"{settings.supabase_url.rstrip('/')}/rest/v1/mandi_monthly"
                "?on_conflict=state,district,commodity,year,month")
    return _post_batches(endpoint, headers, payload)


# --------------------------------------------------------------------------- #
# Monthly refresh
# --------------------------------------------------------------------------- #
def _month_pairs(today: Optional[date] = None) -> List[Tuple[int, int]]:
    """Current and previous month — the only ones AGMARKNET can still revise."""
    d = today or date.today()
    first = d.replace(day=1)
    prev = first - timedelta(days=1)
    return [(first.year, first.month), (prev.year, prev.month)]


def refresh_monthly(states: Optional[Iterable[str]] = None, delay: float = 0.4,
                    months: Optional[List[Tuple[int, int]]] = None) -> dict:
    """Re-fetch the current + previous month averages for existing pairs."""
    import agmarknet_monthly as am

    ref = am.load_ref()
    wanted = {s.strip().lower() for s in states or [] if s.strip()}
    pairs = _db().execute(
        "SELECT DISTINCT state, commodity FROM mandi_monthly"
    ).fetchall()
    pairs = [(r["state"], r["commodity"]) for r in pairs
             if not wanted or r["state"].lower() in wanted]
    months = months or _month_pairs()

    def one(pair: Tuple[str, str]) -> int:
        state, crop = pair
        sid, cid = am.state_id(ref, state), am.commodity_id(ref, crop)
        if not sid or not cid:
            return 0
        try:
            return am.ingest(state, sid, crop, cid, months, delay=delay)
        except Exception as exc:  # noqa: BLE001 - one pair must not kill the run
            print(f"  monthly refresh failed for {state}/{crop}: {exc}", file=sys.stderr)
            return 0

    written = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        for n in pool.map(one, pairs):
            written += n
    return {"pairs": len(pairs), "rows": written,
            "months": [f"{y}-{m:02d}" for y, m in months]}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run(monthly: bool = False, push_only: bool = False,
        states: Optional[Sequence[str]] = None, prune_keep: Optional[int] = None,
        prune_dry_run: bool = False) -> int:
    t0 = time.time()
    failures: List[str] = []
    print("=== FarmIntel sync ===")

    if not push_only:
        try:
            live = daily_ingest.run_local(goa=False)
            print(f"[1/3 daily]   {live}")
        except Exception as exc:  # noqa: BLE001
            print(f"[1/3 daily]   FAILED: {exc}", file=sys.stderr)
            failures.append("daily ingest")

    if not push_only:
        try:
            derived = price_store.monthly_from_daily()
            print(f"[2/3 monthly] derived {derived} rows from daily observations")
        except Exception as exc:  # noqa: BLE001
            print(f"[2/3 monthly] derive FAILED: {exc}", file=sys.stderr)
            failures.append("monthly derive")

    if monthly and not push_only:
        try:
            info = refresh_monthly(states=states)
            print(f"[2/3 portal]  {info}")
        except Exception as exc:  # noqa: BLE001
            print(f"[2/3 portal]  FAILED: {exc}", file=sys.stderr)
            failures.append("portal monthly refresh")

    if not settings.supabase_url or not settings.supabase_service_key:
        print("[mirror] skipped: SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        failures.append("supabase not configured")
    else:
        daily_rows = daily_ingest.supabase_mirror(limit_days=3)
        if daily_rows == 0:
            failures.append("daily mirror")
        monthly_rows, errs = push_monthly(everything=push_only and not monthly)
        failures.extend(errs)
        print(f"[3/3 mirror]  daily rows={daily_rows} monthly rows={monthly_rows}")

    if prune_keep:
        try:
            info = price_store.prune_monthly(keep_months=prune_keep, dry_run=prune_dry_run)
            print(f"[prune]       {info}")
        except Exception as exc:  # noqa: BLE001
            print(f"[prune]       FAILED: {exc}", file=sys.stderr)
            failures.append("prune")

    cov = price_store.coverage()
    mcov = price_store.monthly_coverage()
    print(f"[local]       daily {cov.get('rows')} rows "
          f"({cov.get('first_date')} → {cov.get('last_date')}), "
          f"monthly {mcov.get('rows')} rows")
    print(f"[done]        {time.time() - t0:.0f}s"
          + (f", problems: {', '.join(failures)}" if failures else ", all steps ok"))
    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portal-monthly", dest="monthly", action="store_true",
                    help=f"also re-fetch AGMARKNET's monthly report ({MAJOR_CROPS_HINT})")
    ap.add_argument("--push-only", action="store_true",
                    help="skip fetching; just re-push both tables to Supabase")
    ap.add_argument("--states", default="",
                    help="limit the portal monthly refresh to these states (comma separated)")
    ap.add_argument("--prune-keep-months", type=int, default=0, metavar="N",
                    help="delete derived monthly rows older than N months (imported rows are kept)")
    ap.add_argument("--prune-dry-run", action="store_true",
                    help="report what --prune-keep-months would delete without deleting")
    args = ap.parse_args(argv)
    states = [s.strip() for s in args.states.split(",") if s.strip()]
    return run(monthly=args.monthly, push_only=args.push_only, states=states,
               prune_keep=args.prune_keep_months or None,
               prune_dry_run=args.prune_dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
