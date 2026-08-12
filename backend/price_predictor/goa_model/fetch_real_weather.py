#!/usr/bin/env python3
"""
Real Weather Data Fetcher for Goa Districts
Uses Open-Meteo ERA5-Land (free, no API key required)
Fetches historical daily weather for model training and prediction
"""

import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings("ignore")

# ─── CONFIG ──────────────────────────────────────────────────────────────
DATA_DIR = Path("/Users/karthik/Desktop/Capstone copy/data/historical_prices/goa_merged")
WEATHER_CACHE_DIR = DATA_DIR / "weather_cache"
WEATHER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Goa district coordinates (approximate centers)
GOA_DISTRICTS_COORDS = {
    "North Goa": {"lat": 15.55, "lon": 73.82, "district": "North Goa"},
    "South Goa": {"lat": 15.25, "lon": 74.05, "district": "South Goa"},
    # Market-level coordinates for finer granularity
    "Mapusa": {"lat": 15.60, "lon": 73.81, "district": "North Goa"},
    "Pernem": {"lat": 15.71, "lon": 73.79, "district": "North Goa"},
    "Sanquelim": {"lat": 15.55, "lon": 73.98, "district": "North Goa"},
    "Valpol": {"lat": 15.53, "lon": 73.95, "district": "North Goa"},
    "Goa State Horticultural Corporation Ltd.": {"lat": 15.50, "lon": 73.85, "district": "North Goa"},
    "Canacona": {"lat": 15.00, "lon": 74.03, "district": "South Goa"},
    "Curchorem": {"lat": 15.25, "lon": 74.12, "district": "South Goa"},
    "Margao": {"lat": 15.28, "lon": 73.96, "district": "South Goa"},
    "Ponda": {"lat": 15.40, "lon": 73.98, "district": "South Goa"},
}

# Open-Meteo API endpoints
HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/era5"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Weather variables to fetch
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min", 
    "temperature_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "relative_humidity_2m_mean",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "soil_temperature_0_to_7cm_mean",
    "soil_moisture_0_to_7cm_mean",
]

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "surface_pressure",
]


def fetch_historical_weather(
    lat: float, 
    lon: float, 
    start_date: str, 
    end_date: str,
    location_name: str
) -> Optional[pd.DataFrame]:
    """
    Fetch historical daily weather from Open-Meteo ERA5-Land.
    Free tier: 10,000 calls/day, no API key needed.
    """
    cache_file = WEATHER_CACHE_DIR / f"{location_name}_{start_date}_{end_date}.parquet"
    
    # Check cache first
    if cache_file.exists():
        print(f"  📦 Loading cached weather for {location_name}")
        return pd.read_parquet(cache_file)
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "Asia/Kolkata",
    }
    
    try:
        print(f"  🌐 Fetching weather for {location_name} ({lat}, {lon})...")
        response = requests.get(HISTORICAL_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "daily" not in data:
            print(f"  ⚠️ No daily data for {location_name}")
            return None
        
        df = pd.DataFrame(data["daily"])
        df["date"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"])
        df["location"] = location_name
        df["lat"] = lat
        df["lon"] = lon
        
        # Rename columns for clarity
        rename_map = {
            "temperature_2m_max": "temp_max",
            "temperature_2m_min": "temp_min",
            "temperature_2m_mean": "temp_avg",
            "precipitation_sum": "precipitation",
            "rain_sum": "rain",
            "snowfall_sum": "snowfall",
            "precipitation_hours": "precip_hours",
            "relative_humidity_2m_mean": "humidity_avg",
            "relative_humidity_2m_max": "humidity_max",
            "relative_humidity_2m_min": "humidity_min",
            "wind_speed_10m_max": "wind_max",
            "wind_gusts_10m_max": "wind_gust_max",
            "shortwave_radiation_sum": "solar_radiation",
            "et0_fao_evapotranspiration": "et0",
            "soil_temperature_0_to_7cm_mean": "soil_temp",
            "soil_moisture_0_to_7cm_mean": "soil_moisture",
        }
        df = df.rename(columns=rename_map)
        
        # Add derived features
        df["temp_range"] = df["temp_max"] - df["temp_min"]
        df["humidity_range"] = df["humidity_max"] - df["humidity_min"]
        df["heat_stress"] = (df["temp_max"] > 35).astype(int)
        df["cold_stress"] = (df["temp_min"] < 18).astype(int)
        df["drought_stress"] = (df["precipitation"] < 1).astype(int)
        df["flood_risk"] = (df["precipitation"] > 50).astype(int)
        
        # Rolling features
        for window in [3, 7, 14, 30]:
            df[f"temp_avg_ma{window}"] = df["temp_avg"].rolling(window, min_periods=1).mean()
            df[f"precipitation_ma{window}"] = df["precipitation"].rolling(window, min_periods=1).sum()
            df[f"humidity_avg_ma{window}"] = df["humidity_avg"].rolling(window, min_periods=1).mean()
            df[f"temp_max_ma{window}"] = df["temp_max"].rolling(window, min_periods=1).max()
        
        # Save cache
        df.to_parquet(cache_file, index=False)
        print(f"  ✅ Saved {len(df)} days to cache")
        
        return df
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching {location_name}: {e}")
        return None
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return None


def fetch_forecast_weather(lat: float, lon: float, days: int = 14, location_name: str = "") -> Optional[pd.DataFrame]:
    """Fetch weather forecast for prediction."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(DAILY_VARS),
        "forecast_days": days,
        "timezone": "Asia/Kolkata",
    }
    
    try:
        response = requests.get(FORECAST_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "daily" not in data:
            return None
        
        df = pd.DataFrame(data["daily"])
        df["date"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"])
        
        rename_map = {
            "temperature_2m_max": "temp_max",
            "temperature_2m_min": "temp_min",
            "temperature_2m_mean": "temp_avg",
            "precipitation_sum": "precipitation",
            "rain_sum": "rain",
            "relative_humidity_2m_mean": "humidity_avg",
            "relative_humidity_2m_max": "humidity_max",
            "relative_humidity_2m_min": "humidity_min",
            "wind_speed_10m_max": "wind_max",
            "shortwave_radiation_sum": "solar_radiation",
            "et0_fao_evapotranspiration": "et0",
        }
        df = df.rename(columns=rename_map)
        
        df["temp_range"] = df["temp_max"] - df["temp_min"]
        df["heat_stress"] = (df["temp_max"] > 35).astype(int)
        df["cold_stress"] = (df["temp_min"] < 18).astype(int)
        df["drought_stress"] = (df["precipitation"] < 1).astype(int)
        df["flood_risk"] = (df["precipitation"] > 50).astype(int)
        
        return df
        
    except Exception as e:
        print(f"Forecast error for {location_name}: {e}")
        return None


def fetch_all_goa_weather(
    start_date: str = "2022-01-01",
    end_date: str = None
) -> Dict[str, pd.DataFrame]:
    """Fetch weather for all Goa districts/markets."""
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"🌤️ Fetching Goa weather from {start_date} to {end_date}")
    print(f"   Locations: {len(GOA_DISTRICTS_COORDS)}")
    
    all_weather = {}
    
    for location_name, coords in GOA_DISTRICTS_COORDS.items():
        df = fetch_historical_weather(
            coords["lat"], coords["lon"],
            start_date, end_date,
            location_name
        )
        if df is not None:
            all_weather[location_name] = df
        time.sleep(0.1)  # Rate limiting
    
    return all_weather


def merge_weather_to_prices(
    prices_df: pd.DataFrame,
    weather_dict: Dict[str, pd.DataFrame],
    location_col: str = "market"
) -> pd.DataFrame:
    """Merge weather data to price DataFrame by market and date."""
    prices = prices_df.copy()
    prices["arrival_date"] = pd.to_datetime(prices["arrival_date"])
    
    weather_dfs = []
    for location, wdf in weather_dict.items():
        wdf = wdf.copy()
        wdf["date"] = pd.to_datetime(wdf["date"])
        wdf["_merge_location"] = location
        weather_dfs.append(wdf)
    
    if not weather_dfs:
        print("⚠️ No weather data to merge")
        return prices
    
    all_weather = pd.concat(weather_dfs, ignore_index=True)
    
    # Merge on date and location
    # Try market first, then district
    prices["_merge_location"] = prices[location_col]
    
    # Weather columns to merge (exclude metadata)
    weather_cols = [c for c in all_weather.columns if c not in ["date", "location", "lat", "lon", "_merge_location"]]
    
    merged = prices.merge(
        all_weather[["date", "_merge_location"] + weather_cols],
        left_on=["arrival_date", "_merge_location"],
        right_on=["date", "_merge_location"],
        how="left",
        suffixes=("", "_weather")
    )
    
    # Fill missing with district-level weather if available
    # For markets without direct weather, use district average
    district_weather = all_weather[all_weather["_merge_location"].isin(["North Goa", "South Goa"])]
    if len(district_weather) > 0:
        district_cols = [c for c in district_weather.columns if c not in ["date", "location", "lat", "lon", "_merge_location"]]
        missing_mask = merged[weather_cols].isna().all(axis=1) if weather_cols else pd.Series(False, index=merged.index)
        if missing_mask.any():
            district_merged = merged[missing_mask].drop(columns=[c for c in weather_cols if c in merged.columns], errors="ignore")
            district_merged = district_merged.merge(
                district_weather[["date", "_merge_location"] + district_cols],
                left_on=["arrival_date", "district"],
                right_on=["date", "_merge_location"],
                how="left",
                suffixes=("", "_district")
            )
            merged.update(district_merged)
    
    merged = merged.drop(columns=["_merge_location", "date"], errors="ignore")
    
    print(f"✅ Merged weather: {len(weather_cols)} weather features added")
    return merged


def build_weather_dataset():
    """Main function to build complete weather dataset for Goa."""
    # Load price data to get date range
    prices_path = DATA_DIR / "goa_merged_historical.parquet"
    if prices_path.exists():
        prices = pd.read_parquet(prices_path)
        prices["arrival_date"] = pd.to_datetime(prices["arrival_date"])
        start_date = prices["arrival_date"].min().strftime("%Y-%m-%d")
        end_date = prices["arrival_date"].max().strftime("%Y-%m-%d")
        print(f"Price data range: {start_date} to {end_date}")
    else:
        start_date = "2022-01-01"
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    # Fetch weather
    weather_dict = fetch_all_goa_weather(start_date, end_date)
    
    # Save combined weather
    if weather_dict:
        combined = pd.concat(weather_dict.values(), ignore_index=True)
        combined.to_parquet(WEATHER_CACHE_DIR / "goa_all_weather.parquet", index=False)
        print(f"\n💾 Saved combined weather: {len(combined)} records")
        
        # Also save as CSV for inspection
        combined.to_csv(WEATHER_CACHE_DIR / "goa_all_weather.csv", index=False)
    
    return weather_dict


if __name__ == "__main__":
    print("=" * 60)
    print("OPEN-METEO WEATHER FETCHER FOR GOA")
    print("=" * 60)
    
    weather_data = build_weather_dataset()
    
    print(f"\n✅ Complete! Fetched weather for {len(weather_data)} locations")
    for loc, df in weather_data.items():
        print(f"   {loc}: {len(df)} days ({df['date'].min()} to {df['date'].max()})")