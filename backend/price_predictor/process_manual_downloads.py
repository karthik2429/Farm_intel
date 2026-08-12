#!/usr/bin/env python3
"""
Process manually downloaded historical CSV files from data.gov.in
Place downloaded files in: data/historical_prices/manual_downloads/
"""

import pandas as pd
from pathlib import Path
import glob

MANUAL_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/manual_downloads")
MASTER_FILE = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/master_historical_prices.parquet")

EXPECTED_COLS = [
    "state", "district", "market", "commodity", "variety", "grade",
    "arrival_date", "min_price", "max_price", "modal_price"
]

def process_manual_file(filepath: Path) -> pd.DataFrame:
    """Process a single manually downloaded CSV."""
    print(f"Processing: {filepath.name}")
    
    try:
        df = pd.read_csv(filepath, low_memory=False)
    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")
        return pd.DataFrame()
    
    print(f"  Shape: {df.shape}, Columns: {list(df.columns)}")
    
    # Standardize column names (data.gov.in uses various formats)
    col_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl in ['state', 'statename', 'state_name']:
            col_map[col] = 'state'
        elif cl in ['district', 'districtname', 'district_name']:
            col_map[col] = 'district'
        elif cl in ['market', 'marketname', 'market_name', 'mandi', 'mandiname']:
            col_map[col] = 'market'
        elif cl in ['commodity', 'commodityname', 'commodity_name', 'crop']:
            col_map[col] = 'commodity'
        elif cl in ['variety', 'varietyname', 'variety_name']:
            col_map[col] = 'variety'
        elif cl in ['grade', 'gradename', 'grade_name']:
            col_map[col] = 'grade'
        elif cl in ['arrival_date', 'arrivaldate', 'date', 'price_date', 'date_of_arrival']:
            col_map[col] = 'arrival_date'
        elif cl in ['min_price', 'minprice', 'minimum_price', 'min_price_rs']:
            col_map[col] = 'min_price'
        elif cl in ['max_price', 'maxprice', 'maximum_price', 'max_price_rs']:
            col_map[col] = 'max_price'
        elif cl in ['modal_price', 'modalprice', 'modal_price_rs', 'price', 'price_rs']:
            col_map[col] = 'modal_price'
    
    df = df.rename(columns=col_map)
    
    # Ensure all expected columns exist
    for col in EXPECTED_COLS:
        if col not in df.columns:
            if col in ['variety', 'grade']:
                df[col] = 'Local' if col == 'variety' else 'FAQ'
            else:
                df[col] = None
    
    df = df[EXPECTED_COLS]
    
    # Clean data
    df['arrival_date'] = pd.to_datetime(df['arrival_date'], format='%d/%m/%Y', errors='coerce')
    for pcol in ['min_price', 'max_price', 'modal_price']:
        df[pcol] = pd.to_numeric(df[pcol], errors='coerce')
    
    df = df.dropna(subset=['arrival_date', 'modal_price', 'commodity', 'district'])
    df = df[(df['modal_price'] > 0) & (df['modal_price'] < 100000)]  # Sanity filter
    
    print(f"  Cleaned: {len(df)} records")
    return df


def merge_all_manual():
    """Merge all manual downloads + existing master."""
    manual_files = list(MANUAL_DIR.glob("*.csv")) + list(MANUAL_DIR.glob("*.xlsx"))
    
    if not manual_files:
        print("No manual files found in:", MANUAL_DIR)
        return
    
    all_dfs = []
    
    for f in manual_files:
        if f.suffix == '.xlsx':
            # Convert xlsx to csv first
            df = pd.read_excel(f)
            csv_path = f.with_suffix('.csv')
            df.to_csv(csv_path, index=False)
            print(f"  Converted {f.name} -> {csv_path.name}")
            df = process_manual_file(csv_path)
        else:
            df = process_manual_file(f)
        
        if not df.empty:
            all_dfs.append(df)
    
    if not all_dfs:
        print("No valid data in manual files")
        return
    
    manual_combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal manual records: {len(manual_combined):,}")
    
    # Load existing master
    if MASTER_FILE.exists():
        master = pd.read_parquet(MASTER_FILE)
        print(f"Existing master: {len(master):,} records")
        
        # Merge and deduplicate
        combined = pd.concat([master, manual_combined], ignore_index=True)
    else:
        combined = manual_combined
    
    # Deduplicate
    combined = combined.drop_duplicates(
        subset=['state', 'district', 'commodity', 'arrival_date'],
        keep='last'
    )
    combined = combined.sort_values(['state', 'district', 'commodity', 'arrival_date'])
    
    # Save
    combined.to_parquet(MASTER_FILE, index=False)
    print(f"\n✅ Master updated: {len(combined):,} records -> {MASTER_FILE}")
    
    # Summary
    print(f"\nDate range: {combined['arrival_date'].min()} to {combined['arrival_date'].max()}")
    print(f"States: {combined['state'].nunique()}")
    print(f"Commodities: {combined['commodity'].nunique()}")
    print(f"Districts: {combined['district'].nunique()}")
    print("\nTop commodities:")
    print(combined['commodity'].value_counts().head(20))
    print("\nPer state:")
    print(combined['state'].value_counts())


if __name__ == "__main__":
    merge_all_manual()