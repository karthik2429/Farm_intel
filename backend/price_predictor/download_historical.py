"""
Historical Price Data Downloader for AGMARKNET
Downloads bulk CSV datasets from data.gov.in for 5 target states.
"""

import os
import requests
import pandas as pd
from pathlib import Path
import time
from datetime import datetime, timedelta

# Target states for price prediction
TARGET_STATES = [
    "Maharashtra",
    "Karnataka", 
    "Punjab",
    "Madhya Pradesh",
    "Andhra Pradesh"
]

# Known AGMARKNET historical dataset URLs on data.gov.in
# These are example patterns - actual URLs need to be found on data.gov.in catalog
HISTORICAL_DATASETS = {
    "maharashtra_2022_2024": "https://data.gov.in/sites/default/files/agmarknet_maharashtra_2022-2024.csv",
    "karnataka_2022_2024": "https://data.gov.in/sites/default/files/agmarknet_karnataka_2022-2024.csv",
    "punjab_2022_2024": "https://data.gov.in/sites/default/files/agmarknet_punjab_2022-2024.csv",
    "madhya_pradesh_2022_2024": "https://data.gov.in/sites/default/files/agmarknet_madhya_pradesh_2022-2024.csv",
    "andhra_pradesh_2022_2024": "https://data.gov.in/sites/default/files/agmarknet_andhra_pradesh_2022-2024.csv",
}

DATA_DIR = Path(__file__).parent.parent / "data" / "historical_prices"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_historical_csvs():
    """Download historical price CSVs for all target states."""
    results = {}
    
    for state_key, url in HISTORICAL_DATASETS.items():
        state_name = state_key.split("_")[0].replace("_", " ").title()
        out_path = DATA_DIR / f"{state_key}.csv"
        
        if out_path.exists():
            print(f"✅ {state_name}: Already downloaded ({out_path})")
            results[state_name] = str(out_path)
            continue
            
        print(f"⬇️  Downloading {state_name} historical data...")
        try:
            response = requests.get(url, timeout=60, stream=True)
            if response.status_code == 200:
                with open(out_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"✅ {state_name}: Saved to {out_path}")
                results[state_name] = str(out_path)
            else:
                print(f"❌ {state_name}: HTTP {response.status_code} - URL may not exist")
                results[state_name] = None
        except Exception as e:
            print(f"❌ {state_name}: Error - {e}")
            results[state_name] = None
        
        time.sleep(1)  # Be polite
    
    return results


def load_and_inspect_csv(filepath):
    """Load a historical CSV and show structure."""
    try:
        df = pd.read_csv(filepath)
        print(f"\n📊 {filepath.name}")
        print(f"   Shape: {df.shape}")
        print(f"   Columns: {list(df.columns)}")
        print(f"   Date range: {df.get('arrival_date', df.get('Arrival_Date', 'N/A'))}")
        print(f"   States: {df.get('state', df.get('State', 'N/A')).unique() if 'state' in df.columns or 'State' in df.columns else 'N/A'}")
        print(f"   Commodities: {df.get('commodity', df.get('Commodity', 'N/A')).nunique() if 'commodity' in df.columns or 'Commodity' in df.columns else 'N/A'}")
        print(f"   Sample:\n{df.head(2)}")
        return df
    except Exception as e:
        print(f"❌ Failed to load {filepath}: {e}")
        return None


def create_synthetic_historical_data():
    """
    Create synthetic historical price data for initial model training.
    Uses seasonal patterns, crop calendars, and realistic price ranges.
    """
    from collab.utils import historical_lookup
    import numpy as np
    
    print("\n🔧 Generating synthetic historical data for training...")
    
    # Commodity base prices (INR per quintal)
    BASE_PRICES = {
        "Onion": 1500, "Tomato": 1200, "Potato": 900,
        "Rice": 2200, "Wheat": 2100, "Maize": 1800,
        "Cotton": 5500, "Soybean": 4000, "Groundnut": 4500,
        "Chilli": 8000, "Turmeric": 7000, "Cumin": 15000,
        "Gram": 4800, "Arhar": 5500, "Moong": 6000, "Urad": 5800,
        "Mustard": 4200, "Sunflower": 3800, "Safflower": 4000,
        "Jowar": 2600, "Bajra": 2200, "Ragi": 2800,
        "Sugarcane": 320, "Jute": 3500,
    }
    
    # Seasonal multipliers (month -> price factor)
    SEASONAL_FACTORS = {
        1: 1.15, 2: 1.10, 3: 1.05,  # Post-harvest (Rabi)
        4: 1.00, 5: 0.95, 6: 0.90,  # Pre-monsoon
        7: 0.85, 8: 0.88, 9: 0.92,  # Kharif sowing
        10: 0.95, 11: 1.00, 12: 1.10,  # Kharif harvest
    }
    
    # State-district mapping for major markets
    MARKETS = {
        "Maharashtra": ["Nashik", "Lasalgaon", "Pune", "Ahmednagar", "Solapur", "Nagpur"],
        "Karnataka": ["Bangalore", "Mysore", "Davangere", "Hubli", "Belgaum"],
        "Punjab": ["Amritsar", "Ludhiana", "Jalandhar", "Patiala", "Bathinda"],
        "Madhya Pradesh": ["Indore", "Bhopal", "Ujjain", "Gwalior", "Jabalpur"],
        "Andhra Pradesh": ["Vijayawada", "Guntur", "Kurnool", "Nellore", "Kakinada"],
    }
    
    # Crops per state (major ones)
    STATE_CROPS = {
        "Maharashtra": ["Onion", "Tomato", "Cotton", "Soybean", "Gram", "Sugarcane", "Maize", "Jowar", "Bajra", "Turmeric"],
        "Karnataka": ["Rice", "Maize", "Ragi", "Cotton", "Groundnut", "Sunflower", "Tomato", "Chilli", "Arecanut", "Coconut"],
        "Punjab": ["Wheat", "Rice", "Cotton", "Maize", "Mustard", "Sugarcane", "Potato", "Kinnow"],
        "Madhya Pradesh": ["Soybean", "Wheat", "Gram", "Mustard", "Maize", "Cotton", "Urad", "Moong"],
        "Andhra Pradesh": ["Rice", "Cotton", "Chilli", "Turmeric", "Maize", "Groundnut", "Bengal Gram", "Black Gram"],
    }
    
    np.random.seed(42)
    all_records = []
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365 * 3)  # 3 years
    
    for state, districts in MARKETS.items():
        crops = STATE_CROPS[state]
        
        for district in districts:
            for crop in crops:
                base_price = BASE_PRICES.get(crop, 2000)
                
                # Generate weekly prices for 3 years
                current = start_date
                while current <= end_date:
                    if np.random.random() < 0.7:  # 70% chance of market day
                        month = current.month
                        day_of_week = current.weekday()
                        
                        # Seasonal factor
                        seasonal = SEASONAL_FACTORS.get(month, 1.0)
                        
                        # Weekly variation (weekend slightly higher)
                        weekly = 1.02 if day_of_week >= 5 else 1.0
                        
                        # Random walk component
                        noise = np.random.lognormal(0, 0.08)
                        
                        # Festival spikes
                        festival_boost = 1.0
                        if month in [10, 11] and current.day in range(1, 15):  # Diwali
                            festival_boost = 1.15
                        elif month == 3 and current.day in range(15, 31):  # Holi
                            festival_boost = 1.10
                        elif month == 8 and current.day in range(15, 31):  # Onam/Rakhi
                            festival_boost = 1.08
                        
                        modal_price = base_price * seasonal * weekly * noise * festival_boost
                        modal_price = max(modal_price * 0.7, min(modal_price * 1.3, modal_price * np.random.uniform(0.95, 1.05)))
                        
                        min_price = modal_price * np.random.uniform(0.85, 0.95)
                        max_price = modal_price * np.random.uniform(1.05, 1.20)
                        arrival = np.random.uniform(50, 5000)
                        
                        all_records.append({
                            "state": state,
                            "district": district,
                            "market": f"{district} APMC",
                            "commodity": crop,
                            "variety": "Local",
                            "grade": "FAQ",
                            "arrival_date": current.strftime("%d/%m/%Y"),
                            "min_price": round(min_price, 2),
                            "max_price": round(max_price, 2),
                            "modal_price": round(modal_price, 2),
                            "arrival_tonnes": round(arrival, 2),
                        })
                    
                    current += timedelta(days=1)
    
    df = pd.DataFrame(all_records)
    out_path = DATA_DIR / "synthetic_historical_3yr.csv"
    df.to_csv(out_path, index=False)
    print(f"✅ Generated {len(df):,} records -> {out_path}")
    print(f"   States: {df['state'].nunique()}, Crops: {df['commodity'].nunique()}, Districts: {df['district'].nunique()}")
    return df


def merge_all_historical_data():
    """Merge all historical CSV files + synthetic data into master dataset."""
    all_dfs = []
    
    # Load real CSVs if they exist
    for csv_file in DATA_DIR.glob("*.csv"):
        if csv_file.name == "synthetic_historical_3yr.csv":
            continue
        df = load_and_inspect_csv(csv_file)
        if df is not None:
            all_dfs.append(df)
    
    # Add synthetic data
    syn_df = create_synthetic_historical_data()
    all_dfs.append(syn_df)
    
    if not all_dfs:
        print("❌ No data to merge")
        return None
    
    # Standardize columns
    standard_cols = ["state", "district", "market", "commodity", "variety", "grade", 
                     "arrival_date", "min_price", "max_price", "modal_price", "arrival_tonnes"]
    
    merged = []
    for df in all_dfs:
        # Map columns to standard names
        col_map = {}
        for c in df.columns:
            c_lower = c.lower().replace(" ", "_")
            if c_lower in ["state", "statename"]:
                col_map[c] = "state"
            elif c_lower in ["district", "dist_name"]:
                col_map[c] = "district"
            elif c_lower in ["market", "market_name", "mandi"]:
                col_map[c] = "market"
            elif c_lower in ["commodity", "commodity_name", "crop"]:
                col_map[c] = "commodity"
            elif c_lower in ["variety", "variety_name"]:
                col_map[c] = "variety"
            elif c_lower in ["grade", "grade_name"]:
                col_map[c] = "grade"
            elif c_lower in ["arrival_date", "date", "price_date"]:
                col_map[c] = "arrival_date"
            elif c_lower in ["min_price", "minimum_price", "minprice"]:
                col_map[c] = "min_price"
            elif c_lower in ["max_price", "maximum_price", "maxprice"]:
                col_map[c] = "max_price"
            elif c_lower in ["modal_price", "modalprice", "price"]:
                col_map[c] = "modal_price"
            elif c_lower in ["arrival_tonnes", "arrival", "quantity", "arrivals"]:
                col_map[c] = "arrival_tonnes"
        
        df_std = df.rename(columns=col_map)
        
        # Ensure all standard columns exist
        for c in standard_cols:
            if c not in df_std.columns:
                if c in ["variety", "grade"]:
                    df_std[c] = "Local" if c == "variety" else "FAQ"
                elif c == "arrival_tonnes":
                    df_std[c] = 0
                else:
                    df_std[c] = None
        
        merged.append(df_std[standard_cols])
    
    master = pd.concat(merged, ignore_index=True)
    
    # Clean and deduplicate
    master["arrival_date"] = pd.to_datetime(master["arrival_date"], format="%d/%m/%Y", errors="coerce")
    master = master.dropna(subset=["arrival_date", "modal_price"])
    master = master.drop_duplicates(subset=["state", "district", "commodity", "arrival_date"])
    master = master.sort_values(["state", "district", "commodity", "arrival_date"])
    
    out_path = DATA_DIR / "master_historical_prices.csv"
    master.to_csv(out_path, index=False)
    print(f"\n✅ Master dataset: {len(master):,} records -> {out_path}")
    print(f"   Date range: {master['arrival_date'].min()} to {master['arrival_date'].max()}")
    print(f"   States: {master['state'].nunique()}")
    print(f"   Commodities: {master['commodity'].nunique()}")
    print(f"   Districts: {master['district'].nunique()}")
    
    return master


if __name__ == "__main__":
    print("=" * 60)
    print("AGMARKNET Historical Price Data Pipeline")
    print("=" * 60)
    
    # Try downloading real CSVs
    download_historical_csvs()
    
    # Merge everything into master dataset
    master = merge_all_historical_data()
    
    if master is not None:
        print("\n✅ Historical data ready for feature engineering!")
    else:
        print("\n❌ No historical data available")