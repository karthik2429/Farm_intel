#!/usr/bin/env python3
"""
Download 2-3 years of historical mandi prices from AGMARKNET API
for 5 major agricultural states.
"""

import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_KEY = "579b464db66ec23bdd0000010b138cdcddfa47526650163ba46d0b07"
BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

TARGET_STATES = [
    "Maharashtra",
    "Karnataka", 
    "Punjab",
    "Madhya Pradesh",
    "Andhra Pradesh"
]

DATA_DIR = Path("historical_price_data")
DATA_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "FarmIntel-PricePrediction/1.0"})

def fetch_page(state: str, offset: int = 0, limit: int = 1000, 
               start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
    """Fetch a single page of data from AGMARKNET API."""
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": offset,
    }
    
    if state:
        params["filters[state]"] = state
    
    if start_date:
        params["filters[arrival_date][gte]"] = start_date
    if end_date:
        params["filters[arrival_date][lte]"] = end_date

    for attempt in range(3):
        try:
            resp = SESSION.get(BASE_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching {state} offset={offset}, attempt {attempt+1}/3")
            time.sleep(5 * (attempt + 1))
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching {state} offset={offset}: {e}, attempt {attempt+1}/3")
            time.sleep(3 * (attempt + 1))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for {state} offset={offset}: {e}")
            time.sleep(3 * (attempt + 1))
    
    return {"records": [], "count": 0, "total": 0}

def download_state_data(state: str, start_date: str = "01/01/2023", 
                        end_date: str = None, max_records: int = 500000) -> pd.DataFrame:
    """Download all historical data for a state with pagination."""
    if end_date is None:
        end_date = datetime.now().strftime("%d/%m/%Y")
    
    logger.info(f"Downloading {state} data from {start_date} to {end_date}")
    
    all_records = []
    offset = 0
    limit = 1000
    total_fetched = 0
    
    while total_fetched < max_records:
        data = fetch_page(state, offset, limit, start_date, end_date)
        records = data.get("records", [])
        
        if not records:
            logger.info(f"No more records for {state} at offset {offset}")
            break
        
        all_records.extend(records)
        total_fetched += len(records)
        offset += limit
        
        logger.info(f"{state}: fetched {total_fetched} records (offset={offset})")
        
        if len(records) < limit:
            break
        
        time.sleep(0.5)  # Rate limiting
    
    if not all_records:
        logger.warning(f"No data retrieved for {state}")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_records)
    logger.info(f"Completed {state}: {len(df)} total records")
    return df

def clean_price_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize the price data."""
    if df.empty:
        return df
    
    # Standardize column names (API returns mixed case)
    col_map = {}
    for col in df.columns:
        lower = col.lower()
        if lower in ['state', 'district', 'market', 'commodity', 'variety', 'grade']:
            col_map[col] = lower.capitalize()
        elif lower == 'arrival_date':
            col_map[col] = 'Arrival_Date'
        elif lower in ['min_price', 'max_price', 'modal_price']:
            col_map[col] = lower.replace('_', '_').capitalize()
    
    df = df.rename(columns=col_map)
    
    # Ensure required columns exist
    required = ['State', 'District', 'Market', 'Commodity', 'Arrival_Date', 'Modal_Price']
    for col in required:
        if col not in df.columns:
            # Try case-insensitive match
            for c in df.columns:
                if c.lower() == col.lower():
                    df = df.rename(columns={c: col})
                    break
    
    # Parse dates
    if 'Arrival_Date' in df.columns:
        df['Arrival_Date'] = pd.to_datetime(df['Arrival_Date'], format='%d/%m/%Y', errors='coerce')
    
    # Numeric prices
    for price_col in ['Min_Price', 'Max_Price', 'Modal_Price']:
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
    
    # Drop rows with missing critical data
    df = df.dropna(subset=['Arrival_Date', 'Modal_Price', 'Commodity', 'District'])
    
    # Sort
    df = df.sort_values(['State', 'Commodity', 'District', 'Market', 'Arrival_Date']).reset_index(drop=True)
    
    return df

def download_all_states():
    """Download data for all target states."""
    start_date = "01/01/2023"  # 3+ years
    end_date = datetime.now().strftime("%d/%m/%Y")
    
    all_dfs = []
    
    for state in TARGET_STATES:
        try:
            df = download_state_data(state, start_date, end_date, max_records=200000)
            if not df.empty:
                df = clean_price_data(df)
                if not df.empty:
                    # Save state file
                    state_file = DATA_DIR / f"{state.replace(' ', '_')}_prices_2023_2026.parquet"
                    df.to_parquet(state_file, index=False)
                    logger.info(f"Saved {state} to {state_file} ({len(df)} rows)")
                    all_dfs.append(df)
            time.sleep(2)  # Be nice to API
        except Exception as e:
            logger.error(f"Failed to download {state}: {e}")
            continue
    
    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        combined_file = DATA_DIR / "combined_5states_prices_2023_2026.parquet"
        combined.to_parquet(combined_file, index=False)
        logger.info(f"Saved combined data: {combined_file} ({len(combined)} rows)")
        
        # Summary stats
        print("\n=== DATA SUMMARY ===")
        print(f"Total records: {len(combined):,}")
        print(f"Date range: {combined['Arrival_Date'].min()} to {combined['Arrival_Date'].max()}")
        print(f"States: {combined['State'].nunique()}")
        print(f"Commodities: {combined['Commodity'].nunique()}")
        print(f"Districts: {combined['District'].nunique()}")
        print(f"Markets: {combined['Market'].nunique()}")
        print("\nTop commodities by record count:")
        print(combined['Commodity'].value_counts().head(20))
        print("\nRecords per state:")
        print(combined['State'].value_counts())

if __name__ == "__main__":
    download_all_states()