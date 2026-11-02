"""
Daily mandi ingest job (Phase 1).

Runs the AGMARKNET live fetch + Goa backfill import into the local SQLite
price store, and — when SUPABASE_URL + SUPABASE_SERVICE_KEY are set —
mirrors the same rows into the shared Supabase mandi_prices table so real
history accrues centrally from CI (see .github/workflows/daily-mandi-ingest.yml).

Usage:
    python daily_ingest.py             # ingest the latest live snapshot
    python daily_ingest.py --goa       # also (re-)import the Goa backfill
    python daily_ingest.py --status    # print store + remote coverage
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

import mandi_ingest
import price_store

BACKEND_DIR = Path(__file__).resolve().parent


def _guess_state(district: str) -> str:
    return price_store.state_for_district(district) or "Unknown"


def run_local(goa: bool) -> dict:
    """Ingest the latest live snapshot (+ Goa backfill when asked).
    The AGMARKNET resource serves a few past days too — the fetch paths are
    idempotent upserts, so re-running is always safe."""
    if goa:
        mandi_ingest.backfill_goa()
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    live = mandi_ingest.ingest_live_once()
    return {"live_rows_upserted": live}


def supabase_mirror(limit_days: int = 3) -> int:
    """Mirror the newest rows from the local store into Supabase.

    Requires SUPABASE_URL (any) and SUPABASE_SERVICE_KEY (service role) in
    the environment. Upserts with on_conflict=date,state,district,market,
    commodity,variety — matching the migration's unique constraint.
    """
    from config import settings

    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_key
    if not url or not key:
        print("[supabase] SUPABASE_URL / SUPABASE_SERVICE_KEY not set — "
              "skipping central mirror (local store only)")
        return 0

    import price_store as ps
    conn = ps._connect()
    rows = conn.execute(
        "SELECT date, state, district, market, commodity, variety, "
        "min_price, max_price, modal_price, source "
        "FROM mandi_prices WHERE date >= date('now', ?)",
        (f"-{limit_days} days",),
    ).fetchall()
    if not rows:
        print("[supabase] no recent local rows to mirror")
        return 0

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    endpoint = f"{url}/rest/v1/mandi_prices"
    payload = [
        {
            "date": r["date"], "state": r["state"], "district": r["district"],
            "market": r["market"], "commodity": r["commodity"],
            "variety": r["variety"],
            "min_price": r["min_price"], "max_price": r["max_price"],
            "modal_price": r["modal_price"], "source": r["source"],
        }
        for r in rows
    ]
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=60)
    if resp.status_code >= 300:
        print(f"[supabase] mirror FAILED {resp.status_code}: {resp.text[:300]}")
        return 0
    print(f"[supabase] mirrored {len(payload)} rows (last {limit_days} days)")
    return len(payload)


def print_status() -> None:
    cov = price_store.coverage()
    print(json.dumps(cov, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goa", action="store_true",
                    help="also (re-)import the Goa historical backfill")
    ap.add_argument("--status", action="store_true",
                    help="only print coverage")
    args = ap.parse_args()

    if args.status:
        print_status()
        return 0

    print("=== FarmIntel daily mandi ingest ===")
    local = run_local(goa=args.goa)
    print(f"[local] {json.dumps(local)}")
    supabase_mirror()
    cov = price_store.coverage()
    print("[coverage]", json.dumps(cov, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
