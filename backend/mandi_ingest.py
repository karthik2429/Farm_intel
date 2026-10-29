"""
Live AGMARKNET ingestion for FarmIntel (Phase 1).

Fetches today's "Current Daily Price of Various Commodities from Various
Markets (Mandi)" records from api.data.gov.in and upserts them into the
price store, so real mandi history accumulates day by day.

Also imports the real Goa 2-year historical parquet into the store so
forecasting has backfill for Goa immediately. (data.gov.in only exposes a
current-day snapshot resource — there is no API for multi-year history —
so the Goa parquet is the only real backfill available, and every other
state starts accumulating from the first successful daily run.)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

import price_store

logger = logging.getLogger("farmintel.ingest")

RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
LIVE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"


def load_env() -> None:
    """Load Farm_intel/.env (KEY=VALUE lines) into os.environ for keys that
    are not already set. No python-dotenv dependency; safe to call twice."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))
    except OSError:
        pass


load_env()

# DATA_GOV_API_KEY from env; never hardcode a key in two places again.
API_KEY = os.environ.get("DATA_GOV_API_KEY", "")

if API_KEY:
    logger.info("DATA_GOV_API_KEY loaded (%s…%s)", API_KEY[:8], API_KEY[-4:])

PAGE_LIMIT = 2000
MAX_ROWS_PER_RUN = int(os.environ.get("FARMINTEL_INGEST_MAX_ROWS", "200000"))
REQUEST_TIMEOUT = 45


def _headers() -> dict:
    return {"User-Agent": "FarmIntel/3.0 (mandi ingestion)", "Accept": "application/json"}


def _parse_date(s) -> Optional[str]:
    """arrival_date arrives as dd/mm/yyyy."""
    try:
        return pd.to_datetime(str(s), format="%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        try:
            return pd.to_datetime(s).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return None


def fetch_live_page(filters: Optional[Dict[str, str]] = None,
                    offset: int = 0, limit: int = PAGE_LIMIT) -> dict:
    params: Dict[str, object] = {"api-key": API_KEY, "format": "json",
                                 "limit": limit, "offset": offset}
    for k, v in (filters or {}).items():
        params[f"filters[{k}]"] = v
    try:
        r = requests.get(LIVE_URL, params=params, headers=_headers(),
                         timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("live fetch failed: %s", e)
        return {}
    if r.status_code != 200:
        logger.warning("live fetch HTTP %s", r.status_code)
        return {}
    try:
        return r.json()
    except ValueError:
        logger.warning("live fetch returned non-JSON")
        return {}


def _normalize_records(records: List[dict], source: str) -> List[dict]:
    out = []
    for rec in records:
        d = _parse_date(rec.get("arrival_date"))
        if not d:
            continue
        out.append({
            "date": d,
            "state": rec.get("state") or "",
            "district": rec.get("district") or "",
            "market": rec.get("market") or "",
            "commodity": rec.get("commodity") or "",
            "variety": rec.get("variety") or "",
            "min_price": rec.get("min_price"),
            "max_price": rec.get("max_price"),
            "modal_price": rec.get("modal_price"),
            "source": source,
        })
    return out


def ingest_live_once(filters: Optional[Dict[str, str]] = None,
                     source: str = "agmarknet_live") -> int:
    """Page through the current daily snapshot and upsert everything."""
    if not API_KEY:
        logger.warning("DATA_GOV_API_KEY not set; skipping live ingest")
        return 0
    collected: List[dict] = []
    offset = 0
    while len(collected) < MAX_ROWS_PER_RUN:
        data = fetch_live_page(filters, offset=offset)
        records = data.get("records") or []
        if not records:
            break
        collected.extend(_normalize_records(records, source))
        total = int(data.get("total") or 0)
        offset += len(records)
        if offset >= total or len(records) < PAGE_LIMIT:
            break
        time.sleep(0.4)
    n = price_store.upsert_many(collected) if collected else 0
    logger.info("ingest_live_once: %d rows upserted", n)
    return n


def ingest_state(state: str) -> int:
    return ingest_live_once({"state": state})


# ---------------------------------------------------------------------------
# Goa backfill import (real 2-year Agmarknet history, bundled parquet)
# ---------------------------------------------------------------------------

def _find_goa_parquet() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("FARMINTEL_DATA_DIR", ".")) / "historical_prices" / "goa_merged",
        Path(__file__).resolve().parents[2] / "data" / "historical_prices" / "goa_merged",
        Path(__file__).resolve().parents[3] / "data" / "historical_prices" / "goa_merged",
    ]
    for c in candidates:
        p = c / "goa_merged_historical.parquet"
        if p.exists():
            return p
    return None


def backfill_goa() -> int:
    """Import the real Goa historical parquet (2024-07 -> 2026-07)."""
    p = _find_goa_parquet()
    if not p:
        logger.info("goa backfill: parquet not found, skipping")
        return 0
    df = pd.read_parquet(p)
    df["arrival_date"] = pd.to_datetime(df["arrival_date"])
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "date": r["arrival_date"].strftime("%Y-%m-%d"),
            "state": r.get("state") or "Goa",
            "district": r.get("district") or "",
            "market": r.get("market") or "",
            "commodity": r.get("commodity") or "",
            "variety": r.get("variety") or "",
            "min_price": r.get("min_price"),
            "max_price": r.get("max_price"),
            "modal_price": r.get("modal_price"),
            "source": "agmarknet_backfill",
        })
    n = price_store.upsert_many(rows)
    logger.info("goa backfill: %d rows imported", n)
    return n


def run_full(update_days_back: int = 0) -> dict:
    """Morning cron entry: import Goa backfill once per day (cheap even when
    idempotent) + fetch today's full national snapshot."""
    start = time.time()
    goa = backfill_goa()
    live = ingest_live_once()
    cov = price_store.coverage()
    cov["goa_rows_upserted"] = goa
    cov["live_rows_upserted"] = live
    cov["seconds"] = round(time.time() - start, 1)
    logger.info("run_full done: %s", cov)
    return cov


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    stats = run_full()
    print(stats)
