#!/usr/bin/env python3
"""
Daily AGMARKNET Price Collector
Run via cron: 0 18 * * * /usr/bin/python3 /path/to/daily_price_collector.py
Collects daily mandi prices for target states and appends to historical CSV.
"""

import os
import sys
import time
import json
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_KEY = "579b464db66ec23bdd0000010b138cdcddfa47526650163ba46d0b07"
BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

TARGET_STATES = [
    "Andhra Pradesh",
    "Karnataka", 
    "Maharashtra",
    "Punjab",
    "Madhya Pradesh"
]

DATA_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MASTER_FILE = DATA_DIR / "master_historical_prices.parquet"
DAILY_FILE = DATA_DIR / f"daily_{datetime.now().strftime('%Y%m%d')}.csv"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "FarmIntel-PriceCollector/1.0"})


def fetch_state_data(state: str, date_str: str) -> List[Dict]:
    """Fetch all records for a state on a specific date."""
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": 5000,
        "filters[state]": state,
        "filters[arrival_date]": date_str,
    }
    
    for attempt in range(3):
        try:
            resp = SESSION.get(BASE_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("records", [])
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching {state} for {date_str}, attempt {attempt+1}/3")
            time.sleep(5 * (attempt + 1))
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching {state} for {date_str}: {e}, attempt {attempt+1}/3")
            time.sleep(3 * (attempt + 1))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON for {state} on {date_str}, attempt {attempt+1}/3")
            time.sleep(3)
    
    return []


def fetch_all_states(date_str: str) -> pd.DataFrame:
    """Fetch data for all target states on a given date."""
    all_records = []
    
    for state in TARGET_STATES:
        logger.info(f"Fetching {state} for {date_str}...")
        records = fetch_state_data(state, date_str)
        logger.info(f"  -> {len(records)} records")
        all_records.extend(records)
        time.sleep(0.5)  # Rate limiting
    
    if not all_records:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_records)
    
    # Standardize columns
    col_map = {
        "state": "state",
        "district": "district", 
        "market": "market",
        "commodity": "commodity",
        "variety": "variety",
        "grade": "grade",
        "arrival_date": "arrival_date",
        "min_price": "min_price",
        "max_price": "max_price", 
        "modal_price": "modal_price",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    
    # Add collection timestamp
    df["collected_at"] = datetime.now().isoformat()
    
    return df


def load_master() -> pd.DataFrame:
    """Load existing master historical data."""
    if MASTER_FILE.exists():
        return pd.read_parquet(MASTER_FILE)
    return pd.DataFrame()


def save_master(df: pd.DataFrame):
    """Save master historical data."""
    df.to_parquet(MASTER_FILE, index=False)
    logger.info(f"Saved master: {len(df):,} records -> {MASTER_FILE}")


def update_historical(date_str: str = None):
    """Main function: fetch daily data and append to master."""
    if date_str is None:
        date_str = datetime.now().strftime("%d/%m/%Y")
    
    logger.info(f"=== Collecting prices for {date_str} ===")
    
    # Fetch new data
    new_df = fetch_all_states(date_str)
    
    if new_df.empty:
        logger.warning("No data collected!")
        return
    
    # Save daily snapshot
    new_df.to_csv(DAILY_FILE, index=False)
    logger.info(f"Saved daily: {len(new_df):,} records -> {DAILY_FILE}")
    
    # Load master and merge
    master = load_master()
    
    if not master.empty:
        # Deduplicate: same state+district+commodity+date keeps latest
        combined = pd.concat([master, new_df], ignore_index=True)
        combined["arrival_date"] = pd.to_datetime(
            combined["arrival_date"], format="%d/%m/%Y", errors="coerce"
        )
        combined = combined.dropna(subset=["arrival_date", "modal_price"])
        combined = combined.drop_duplicates(
            subset=["state", "district", "commodity", "arrival_date"],
            keep="last"
        )
        combined = combined.sort_values(["state", "district", "commodity", "arrival_date"])
    else:
        combined = new_df
    
    save_master(combined)
    
    # Summary
    logger.info(f"Master now has {len(combined):,} records")
    logger.info(f"Date range: {combined['arrival_date'].min()} to {combined['arrival_date'].max()}")
    logger.info(f"States: {combined['state'].nunique()}, Commodities: {combined['commodity'].nunique()}")


def backfill_date_range(start_date: str, end_date: str):
    """Backfill historical data for a date range (use sparingly - API may not support old dates)."""
    start = datetime.strptime(start_date, "%d/%m/%Y")
    end = datetime.strptime(end_date, "%d/%m/%Y")
    
    current = start
    while current <= end:
        date_str = current.strftime("%d/%m/%Y")
        logger.info(f"Backfilling {date_str}...")
        update_historical(date_str)
        current += timedelta(days=1)
        time.sleep(2)  # Be nice to API


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Daily AGMARKNET Price Collector")
    parser.add_argument("--date", help="Date to collect (DD/MM/YYYY), default: today")
    parser.add_argument("--backfill-start", help="Start date for backfill (DD/MM/YYYY)")
    parser.add_argument("--backfill-end", help="End date for backfill (DD/MM/YYYY)")
    
    args = parser.parse_args()
    
    if args.backfill_start and args.backfill_end:
        backfill_date_range(args.backfill_start, args.backfill_end)
    else:
        date_str = args.date or datetime.now().strftime("%d/%m/%Y")
        update_historical(date_str)