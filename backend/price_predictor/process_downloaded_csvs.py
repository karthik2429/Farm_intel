#!/usr/bin/env python3
"""
Process downloaded AGMARKNET historical price CSVs into a unified training dataset.
Handles both: single state-level CSV OR multiple district-level CSVs per state.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import glob
import re

# ─── CONFIG ──────────────────────────────────────────────────────────────
DOWNLOAD_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/manual_downloads")
OUTPUT_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_STATES = ["Andhra Pradesh", "Karnataka", "Maharashtra", "Punjab", "Madhya Pradesh"]

# Standard column mapping (handle variations in downloaded CSVs)
COL_MAP = {
    # Date columns
    "arrival_date": "Arrival_Date",
    "arrival date": "Arrival_Date",
    "date": "Arrival_Date",
    "date of arrival": "Arrival_Date",
    
    # Location
    "state": "State",
    "state name": "State",
    "statename": "State",
    "district": "District",
    "district name": "District",
    "distname": "District",
    "market": "Market",
    "market name": "Market",
    "mandi": "Market",
    "mandi name": "Market",
    
    # Commodity
    "commodity": "Commodity",
    "commodity name": "Commodity",
    "crop": "Commodity",
    "crop name": "Commodity",
    "variety": "Variety",
    "variety name": "Variety",
    "grade": "Grade",
    
    # Prices
    "min_price": "Min_Price",
    "min price": "Min_Price",
    "minimum price": "Min_Price",
    "max_price": "Max_Price",
    "max price": "Max_Price",
    "maximum price": "Max_Price",
    "modal_price": "Modal_Price",
    "modal price": "Modal_Price",
    "modal": "Modal_Price",
    "price": "Modal_Price",
    
    # Arrivals
    "arrival": "Arrivals",
    "arrivals": "Arrivals",
    "arrival_tonnes": "Arrivals",
    "quantity": "Arrivals",
    "arrival (tonnes)": "Arrivals",
    "arrival (in tonnes)": "Arrivals",
}

REQUIRED_COLS = ["State", "District", "Market", "Commodity", "Arrival_Date", "Modal_Price"]
OPTIONAL_COLS = ["Variety", "Grade", "Min_Price", "Max_Price", "Arrivals"]


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map various column name formats to standard names."""
    df = df.copy()
    
    # Lowercase all columns for matching
    col_mapping = {}
    for col in df.columns:
        col_lower = col.strip().lower()
        if col_lower in COL_MAP:
            col_mapping[col] = COL_MAP[col_lower]
        else:
            # Try partial match
            for k, v in COL_MAP.items():
                if k in col_lower:
                    col_mapping[col] = v
                    break
    
    df = df.rename(columns=col_mapping)
    
    # Ensure required columns exist
    for rc in REQUIRED_COLS:
        if rc not in df.columns:
            # Try case-insensitive
            for c in df.columns:
                if c.lower() == rc.lower():
                    df = df.rename(columns={c: rc})
                    break
    
    return df


def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Parse Arrival_Date with multiple format attempts."""
    df = df.copy()
    
    if "Arrival_Date" not in df.columns:
        print("  ⚠️ No Arrival_Date column found")
        return df
    
    # Try multiple date formats
    date_formats = [
        "%d/%m/%Y",      # 13/07/2024
        "%d-%m-%Y",      # 13-07-2024
        "%Y-%m-%d",      # 2024-07-13
        "%d/%m/%y",      # 13/07/24
        "%d-%m-%y",      # 13-07-24
        "%d.%m.%Y",      # 13.07.2024
    ]
    
    parsed = pd.Series(pd.NaT, index=df.index)
    for fmt in date_formats:
        mask = parsed.isna()
        if not mask.any():
            break
        try:
            parsed[mask] = pd.to_datetime(df.loc[mask, "Arrival_Date"], format=fmt, errors="coerce")
        except:
            pass
    
    # Final fallback
    if parsed.isna().any():
        parsed = pd.to_datetime(df["Arrival_Date"], errors="coerce")
    
    df["Arrival_Date"] = parsed
    df["Year"] = df["Arrival_Date"].dt.year
    df["Month"] = df["Arrival_Date"].dt.month
    df["Day"] = df["Arrival_Date"].dt.day
    df["DayOfWeek"] = df["Arrival_Date"].dt.dayofweek
    df["WeekOfYear"] = df["Arrival_Date"].dt.isocalendar().week
    
    return df


def parse_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Parse price columns to numeric."""
    df = df.copy()
    
    for col in ["Min_Price", "Max_Price", "Modal_Price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    
    if "Arrivals" in df.columns:
        df["Arrivals"] = pd.to_numeric(df["Arrivals"].astype(str).str.replace(",", ""), errors="coerce")
    
    # Ensure Modal_Price exists
    if "Modal_Price" not in df.columns:
        if "Min_Price" in df.columns and "Max_Price" in df.columns:
            df["Modal_Price"] = (df["Min_Price"] + df["Max_Price"]) / 2
        else:
            df["Modal_Price"] = np.nan
    
    return df


def clean_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Clean string columns."""
    df = df.copy()
    
    str_cols = ["State", "District", "Market", "Commodity", "Variety", "Grade"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
            df[col] = df[col].replace({"Nan": np.nan, "None": np.nan, "Null": np.nan})
    
    return df


def filter_target_states(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only target states."""
    if "State" not in df.columns:
        return df
    
    # Normalize state names
    state_map = {
        "Keralam": "Kerala",
        "Mp": "Madhya Pradesh",
        "Ap": "Andhra Pradesh",
        "Up": "Uttar Pradesh",
    }
    df["State"] = df["State"].replace(state_map)
    
    before = len(df)
    df = df[df["State"].isin(TARGET_STATES)].copy()
    after = len(df)
    
    if before != after:
        print(f"  📍 Filtered to target states: {before:,} → {after:,} rows")
    
    return df


def add_seasonal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add agricultural season and festival features."""
    df = df.copy()
    
    if "Month" not in df.columns:
        return df
    
    # Indian agricultural seasons
    def get_season(month):
        if month in [6, 7, 8, 9, 10]:
            return "Kharif"
        elif month in [11, 12, 1, 2, 3]:
            return "Rabi"
        else:
            return "Zaid"
    
    df["Season"] = df["Month"].apply(get_season)
    
    # Major festival periods (price impact windows)
    festival_windows = {
        "Diwali": [(10, 15), (11, 15)],      # Oct-Nov
        "Holi": [(3, 1), (3, 31)],           # March
        "Pongal_Sankranti": [(1, 1), (1, 20)], # Jan
        "Eid": [(4, 1), (4, 30), (6, 1), (6, 30)],  # Approx
        "Onam": [(8, 15), (9, 15)],          # Aug-Sep
        "Navratri": [(9, 15), (10, 15)],     # Sep-Oct
    }
    
    df["Festival_Period"] = 0
    for fest, windows in festival_windows.items():
        for (start_m, start_d), (end_m, end_d) in zip(windows[::2], windows[1::2]):
            mask = (
                ((df["Month"] > start_m) | ((df["Month"] == start_m) & (df["Day"] >= start_d))) &
                ((df["Month"] < end_m) | ((df["Month"] == end_m) & (df["Day"] <= end_d)))
            )
            df.loc[mask, "Festival_Period"] = 1
    
    return df


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add price-derived features for ML."""
    df = df.copy()
    
    # Sort for rolling calculations
    df = df.sort_values(["State", "Commodity", "District", "Market", "Arrival_Date"]).reset_index(drop=True)
    
    # Group by commodity-market for rolling stats
    group_cols = ["State", "Commodity", "District", "Market"]
    
    for window in [3, 7, 14, 30]:
        df[f"Modal_Price_MA_{window}"] = df.groupby(group_cols)["Modal_Price"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        df[f"Modal_Price_STD_{window}"] = df.groupby(group_cols)["Modal_Price"].transform(
            lambda x: x.rolling(window, min_periods=1).std()
        )
        df[f"Arrivals_MA_{window}"] = df.groupby(group_cols)["Arrivals"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        ) if "Arrivals" in df.columns else np.nan
    
    # Price momentum
    df["Price_Change_1d"] = df.groupby(group_cols)["Modal_Price"].transform(lambda x: x.pct_change(1))
    df["Price_Change_7d"] = df.groupby(group_cols)["Modal_Price"].transform(lambda x: x.pct_change(7))
    
    # Volatility
    df["Price_Volatility_7d"] = df.groupby(group_cols)["Price_Change_1d"].transform(
        lambda x: x.rolling(7, min_periods=2).std()
    )
    
    return df


def process_file(filepath: Path) -> pd.DataFrame:
    """Process a single CSV file."""
    print(f"\n📄 Processing: {filepath.name}")
    
    try:
        # Try different encodings
        for enc in ["utf-8", "latin-1", "cp1252", "iso-8859-1"]:
            try:
                df = pd.read_csv(filepath, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
        else:
            print(f"  ❌ Failed to read {filepath}")
            return pd.DataFrame()
        
        print(f"  Raw shape: {df.shape}, Columns: {list(df.columns)}")
        
        # Standardize
        df = standardize_columns(df)
        df = parse_dates(df)
        df = parse_prices(df)
        df = clean_strings(df)
        df = filter_target_states(df)
        
        if df.empty:
            print(f"  ⚠️ No target state data in {filepath.name}")
            return pd.DataFrame()
        
        # Drop rows missing critical data
        df = df.dropna(subset=["Arrival_Date", "Modal_Price", "Commodity", "District"])
        
        # Add features
        df = add_seasonal_features(df)
        df = add_price_features(df)
        
        print(f"  ✅ Processed: {len(df):,} rows, {df['State'].nunique()} states, {df['Commodity'].nunique()} commodities")
        return df
        
    except Exception as e:
        print(f"  ❌ Error processing {filepath}: {e}")
        return pd.DataFrame()


def main():
    print("=" * 60)
    print("AGMARKNET Historical Price Data Processor")
    print("=" * 60)
    
    # Find all CSV files in download directory
    csv_files = list(DOWNLOAD_DIR.glob("*.csv")) + list(DOWNLOAD_DIR.glob("**/*.csv"))
    
    if not csv_files:
        print(f"\n❌ No CSV files found in {DOWNLOAD_DIR}")
        print("Please download CSVs from data.gov.in and place them there.")
        return
    
    print(f"\n📁 Found {len(csv_files)} CSV file(s)")
    
    all_dfs = []
    for f in csv_files:
        df = process_file(f)
        if not df.empty:
            all_dfs.append(df)
    
    if not all_dfs:
        print("\n❌ No valid data processed")
        return
    
    # Merge all
    print("\n🔗 Merging all files...")
    merged = pd.concat(all_dfs, ignore_index=True)
    
    # Deduplicate (same market, commodity, date)
    merged = merged.drop_duplicates(
        subset=["State", "District", "Market", "Commodity", "Arrival_Date"],
        keep="last"
    ).sort_values(["State", "Commodity", "District", "Market", "Arrival_Date"]).reset_index(drop=True)
    
    print(f"\n📊 Merged dataset: {len(merged):,} rows")
    print(f"   Date range: {merged['Arrival_Date'].min()} to {merged['Arrival_Date'].max()}")
    print(f"   States: {merged['State'].nunique()}")
    print(f"   Commodities: {merged['Commodity'].nunique()}")
    print(f"   Districts: {merged['District'].nunique()}")
    print(f"   Markets: {merged['Market'].nunique()}")
    
    # Save outputs
    print("\n💾 Saving outputs...")
    
    # Full dataset (Parquet for efficiency)
    full_path = OUTPUT_DIR / "merged_5states_historical.parquet"
    merged.to_parquet(full_path, index=False)
    print(f"  ✅ Full dataset: {full_path} ({full_path.stat().st_size / 1e6:.1f} MB)")
    
    # CSV sample for inspection
    sample_path = OUTPUT_DIR / "merged_5states_historical_sample.csv"
    merged.head(10000).to_csv(sample_path, index=False)
    print(f"  ✅ Sample CSV: {sample_path}")
    
    # Per-state files
    for state in TARGET_STATES:
        state_df = merged[merged["State"] == state]
        if len(state_df) > 0:
            sp = OUTPUT_DIR / f"{state.replace(' ', '_')}_historical.parquet"
            state_df.to_parquet(sp, index=False)
            print(f"  ✅ {state}: {len(state_df):,} rows → {sp}")
    
    # Commodity summary
    print("\n📈 Top 30 commodities by record count:")
    print(merged["Commodity"].value_counts().head(30).to_string())
    
    # State summary
    print("\n📍 Records per state:")
    print(merged["State"].value_counts().to_string())
    
    print("\n✅ Processing complete!")


if __name__ == "__main__":
    main()