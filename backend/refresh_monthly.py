"""
Recompute the shared monthly averages from the daily rows — server side.

The daily workflow writes real observations into public.mandi_prices. This calls
the `refresh_monthly_from_daily` Postgres function (see
supabase/migrations/20261103_refresh_monthly.sql) so the monthly series follows
the daily data without scraping AGMARKNET's monthly report again.

    python refresh_monthly.py                 # runs on the shared project
    MONTHLY_MIN_DAYS=15 python refresh_monthly.py

A month is only written once it has MONTHLY_MIN_DAYS distinct observed days, and
an average published by AGMARKNET is never overwritten — both guards live in the
SQL function, so they hold even when this script is not the caller.

Exits 0 when the function ran (or Supabase is not configured), 1 on failure.
"""
from __future__ import annotations

import os
import sys

import requests

from config import settings


def main() -> int:
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_key
    if not url or not key:
        print("[monthly] SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping")
        return 0

    min_days = int(os.environ.get("MONTHLY_MIN_DAYS", "10"))
    try:
        resp = requests.post(
            f"{url}/rest/v1/rpc/refresh_monthly_from_daily",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"p_min_days": min_days},
            timeout=180,
        )
    except requests.RequestException as exc:
        print(f"[monthly] request failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    if resp.status_code >= 300:
        print(f"[monthly] failed {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        if resp.status_code == 404:
            print("[monthly] the SQL function is missing — run "
                  "supabase/migrations/20261103_refresh_monthly.sql", file=sys.stderr)
        return 1

    print(f"[monthly] {resp.json()} rows derived/updated from daily observations "
          f"(min {min_days} days per month)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
