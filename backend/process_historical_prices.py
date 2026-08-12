#!/usr/bin/env python3
"""
Process manually downloaded historical price CSVs from data.gov.in
for 5 states: AP, Karnataka, Maharashtra, Punjab, Madhya Pradesh
"""

import pandas as pd
import numpy as np
from pathlib import Path
import glob

DATA_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/manual_downloads")
OUTPUT_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILES = {
    "Andhra Pradesh": "ap_prices_2024_2026.csv",
    "Karnataka": "ka_prices_2024_2026.csv",
    "Maharashtra": "mh_prices_2024_2026.csv",
    "Punjab": "pb_prices_2024_2026.csv",
    "Madhya Pradesh": "mp_prices_2024_2026.csv",
}

def clean_column_name(col: str) -> str:
    """Standardize column names across different CSV formats."""
    col = col.strip().lower().replace(' ', '_').replace('.', '').replace('-', '_')
    col = col.replace('(', '').replace(')', '').replace('/', '_')
    return col

def load_and_clean(filepath: Path, state_name: str) -> pd.DataFrame:
    """Load a state CSV and standardize columns."""
    print(f"\nLoading {state_name} from {filepath.name}...")
    
    try:
        df = pd.read_csv(filepath, low_memory=False)
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        return pd.DataFrame()
    
    print(f"  Raw shape: {df.shape}, Columns: {list(df.columns)}")
    
    # Standardize column names
    df.columns = [clean_column_name(c) for c in df.columns]
    
    # Map common variations to standard names
    col_map = {}
    for col in df.columns:
        cl = col.lower()
        if 'state' in cl and 'state' not in [v for v in col_map.values()]:
            col_map[col] = 'state'
        elif 'district' in cl:
            col_map[col] = 'district'
        elif 'market' in cl or 'mandi' in cl:
            col_map[col] = 'market'
        elif 'commodity' in cl or 'crop' in cl:
            col_map[col] = 'commodity'
        elif 'variety' in cl:
            col_map[col] = 'variety'
        elif 'grade' in cl:
            col_map[col] = 'grade'
        elif 'arrival' in cl and 'date' in cl:
            col_map[col] = 'arrival_date'
        elif 'min' in cl and 'price' in cl:
            col_map[col] = 'min_price'
        elif 'max' in cl and 'price' in cl:
            col_map[col] = 'max_price'
        elif 'modal' in cl and 'price' in cl:
            col_map[col] = 'modal_price'
        elif 'price' in cl and 'modal' not in cl and 'min' not in cl and 'max' not in cl:
            col_map[col] = 'modal_price'
    
    df = df.rename(columns=col_map)
    
    # Ensure required columns
    required = ['state', 'district', 'market', 'commodity', 'arrival_date', 'modal_price']
    for col in required:
        if col not in df.columns:
            print(f"  WARNING: Missing required column: {col}")
            if col == 'state':
                df[col] = state_name
            elif col == 'modal_price':
                # Try to find any price column
                price_cols = [c for c in df.columns if 'price' in c]
                if price_cols:
                    df[col] = df[price_cols[0]]
                else:
                    return pd.DataFrame()
    
    # Parse dates
    date_cols = [c for c in df.columns if 'date' in c]
    for dc in date_cols:
        df[dc] = pd.to_datetime(df[dc], errors='coerce', dayfirst=True)
    
    if 'arrival_date' not in df.columns:
        for dc in date_cols:
            if dc != 'arrival_date':
                df = df.rename(columns={dc: 'arrival_date'})
                break
    
    df['arrival_date'] = pd.to_datetime(df['arrival_date'], errors='coerce', dayfirst=True)
    
    # Parse prices
    for pc in ['min_price', 'max_price', 'modal_price']:
        if pc in df.columns:
            df[pc] = pd.to_numeric(df[pc], errors='coerce')
    
    # Use modal_price as primary, fallback to min/max
    if 'modal_price' not in df.columns or df['modal_price'].isna().all():
        if 'min_price' in df.columns:
            df['modal_price'] = df['min_price']
        elif 'max_price' in df.columns:
            df['modal_price'] = df['max_price']
    
    # Clean
    df = df.dropna(subset=['arrival_date', 'modal_price', 'commodity', 'district'])
    df = df[df['modal_price'] > 0]
    
    # Filter date range
    start_date = pd.Timestamp('2024-07-13')
    end_date = pd.Timestamp('2026-07-12')
    df = df[(df['arrival_date'] >= start_date) & (df['arrival_date'] <= end_date)]
    
    # Add state if missing
    if 'state' not in df.columns or df['state'].isna().all():
        df['state'] = state_name
    
    # Select and sort
    keep_cols = ['state', 'district', 'market', 'commodity', 'variety', 'grade', 
                 'arrival_date', 'min_price', 'max_price', 'modal_price']
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols].sort_values(['commodity', 'district', 'market', 'arrival_date']).reset_index(drop=True)
    
    print(f"  Cleaned: {len(df)} records, {df['commodity'].nunique()} commodities, {df['district'].nunique()} districts")
    print(f"  Date range: {df['arrival_date'].min()} to {df['arrival_date'].max()}")
    
    return df

def create_daily_series(df: pd.DataFrame) -> pd.DataFrame:
    """Create daily price series per commodity-district-market."""
    print("\nCreating daily price series...")
    
    # Group by commodity, district, market, date -> median modal_price
    daily = df.groupby(['state', 'commodity', 'district', 'market', 'arrival_date'], as_index=False)['modal_price'].median()
    
    # Pivot to wide format for time series
    daily_pivot = daily.pivot_table(
        index=['state', 'commodity', 'district', 'market'],
        columns='arrival_date',
        values='modal_price',
        aggfunc='median'
    ).reset_index()
    
    daily_pivot.columns.name = None
    print(f"Daily series shape: {daily_pivot.shape}")
    
    return daily_pivot

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag features, rolling stats for ML."""
    print("\nAdding ML features...")
    
    date_cols = [c for c in df.columns if isinstance(c, pd.Timestamp)]
    date_cols = sorted(date_cols)
    
    # Melt back to long format for feature engineering
    id_cols = ['state', 'commodity', 'district', 'market']
    long_df = df.melt(id_vars=id_cols, value_vars=date_cols, 
                      var_name='date', value_name='price')
    long_df = long_df.dropna(subset=['price']).sort_values(id_cols + ['date']).reset_index(drop=True)
    
    # Features per group
    groups = long_df.groupby(id_cols)
    
    long_df['price_lag_1'] = groups['price'].shift(1)
    long_df['price_lag_7'] = groups['price'].shift(7)
    long_df['price_lag_14'] = groups['price'].shift(14)
    long_df['price_lag_30'] = groups['price'].shift(30)
    
    long_df['rolling_mean_7'] = groups['price'].transform(lambda x: x.rolling(7, min_periods=1).mean())
    long_df['rolling_std_7'] = groups['price'].transform(lambda x: x.rolling(7, min_periods=1).std())
    long_df['rolling_mean_14'] = groups['price'].transform(lambda x: x.rolling(14, min_periods=1).mean())
    long_df['rolling_mean_30'] = groups['price'].transform(lambda x: x.rolling(30, min_periods=1).mean())
    
    long_df['price_change_1d'] = groups['price'].pct_change(1)
    long_df['price_change_7d'] = groups['price'].pct_change(7)
    
    # Calendar features
    long_df['day_of_week'] = long_df['date'].dt.dayofweek
    long_df['month'] = long_df['date'].dt.month
    long_df['quarter'] = long_df['date'].dt.quarter
    long_df['is_month_start'] = long_df['date'].dt.is_month_start.astype(int)
    long_df['is_month_end'] = long_df['date'].dt.is_month_end.astype(int)
    
    # Season (Kharif/Rabi/Zaid)
    def get_season(m):
        if m in [6, 7, 8, 9, 10]: return 'kharif'
        elif m in [11, 12, 1, 2, 3]: return 'rabi'
        else: return 'zaid'
    
    long_df['season'] = long_df['month'].apply(get_season)
    
    print(f"Features shape: {long_df.shape}")
    return long_df

def main():
    print("=" * 60)
    print("PROCESSING HISTORICAL MANDI PRICES (5 STATES)")
    print("=" * 60)
    
    all_dfs = []
    
    for state, filename in STATE_FILES.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"\n⚠️  MISSING: {filename} for {state}")
            continue
        
        df = load_and_clean(filepath, state)
        if not df.empty:
            all_dfs.append(df)
    
    if not all_dfs:
        print("\n❌ No data files found! Please download CSVs to:")
        print(f"   {DATA_DIR}")
        print("   Required files:", list(STATE_FILES.values()))
        return
    
    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\n{'='*60}")
    print(f"COMBINED: {len(combined):,} records")
    print(f"States: {combined['state'].nunique()}")
    print(f"Commodities: {combined['commodity'].nunique()}")
    print(f"Districts: {combined['district'].nunique()}")
    print(f"Markets: {combined['market'].nunique()}")
    print(f"Date range: {combined['arrival_date'].min()} to {combined['arrival_date'].max()}")
    
    # Save cleaned combined
    combined_path = OUTPUT_DIR / "combined_5states_clean.parquet"
    combined.to_parquet(combined_path, index=False)
    print(f"\nSaved cleaned data: {combined_path}")
    
    # Create daily series
    daily = create_daily_series(combined)
    daily_path = OUTPUT_DIR / "daily_price_series.parquet"
    daily.to_parquet(daily_path, index=False)
    print(f"Saved daily series: {daily_path}")
    
    # Add ML features
    featured = add_features(daily)
    featured_path = OUTPUT_DIR / "featured_price_data.parquet"
    featured.to_parquet(featured_path, index=False)
    print(f"Saved featured data: {featured_path}")
    
    # Summary stats
    print(f"\n{'='*60}")
    print("TOP COMMODITIES BY RECORD COUNT:")
    print(combined['commodity'].value_counts().head(20))
    
    print(f"\nRECORDS PER STATE:")
    print(combined['state'].value_counts())
    
    print(f"\n✅ Processing complete! Ready for model training.")
    print(f"   Next step: python train_price_model.py")

if __name__ == "__main__":
    main()