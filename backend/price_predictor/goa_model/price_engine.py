"""
FarmIntel price prediction engine.

Wraps the trained Goa XGBoost model (goa_xgb_model.pkl) with the exact
feature-engineering pipeline from api_v3.py, running it over the merged
Goa historical prices parquet + real Open-Meteo ERA5 weather cache.

Exposes plain functions so main.py can serve the frontend contracts:
  - predict_14d(filters)      -> list of prediction dicts
  - trajectory(filters, days) -> list of {current_price, trajectory}
  - single(filters)           -> prediction + confidence/factors
  - known_commodities() / known_markets()
"""

from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

# ─── Paths (project-root data dir, overridable via env) ─────────────────
import os

_GOA_DIR = Path(__file__).resolve().parent  # .../backend/price_predictor/goa_model

def _find_data_dir() -> Path:
    env = os.environ.get("FARMINTEL_DATA_DIR")
    candidates = []
    if env:
        candidates.append(Path(env))
    # goa_model -> price_predictor -> backend -> Farm_intel -> project root
    root = _GOA_DIR.parents[3]
    candidates.append(root / "data" / "historical_prices" / "goa_merged")
    # legacy absolute layout used during development
    candidates.append(Path.home() / "Desktop" / "Capstone copy" / "data" / "historical_prices" / "goa_merged")
    for c in candidates:
        if (c / "goa_merged_historical.parquet").exists():
            return c
    return candidates[-1]

DATA_DIR = _find_data_dir()
MODEL_DIR = _GOA_DIR
WEATHER_CACHE = DATA_DIR / "weather_cache"

GROUP_COLS = ["district", "commodity", "market"]
MONSOON_MONTHS = [6, 7, 8, 9]
POST_MONSOON_MONTHS = [10, 11]
WINTER_MONTHS = [12, 1, 2]
SUMMER_MONTHS = [3, 4, 5]

GOA_FESTIVALS = {
    "carnival": (2, 1, 2, 15), "shigmo": (3, 1, 3, 31),
    "ganesh_chaturthi": (8, 15, 9, 15), "diwali": (10, 15, 11, 15),
    "christmas": (12, 20, 12, 31), "new_year": (1, 1, 1, 5),
    "sao_joao": (6, 20, 6, 30),
}

COMMODITY_CATEGORIES = {
    "perishable": ["Tomato", "Onion", "Potato", "Banana", "Papaya", "Mango", "Pineapple",
                   "Watermelon", "Green Chilli", "Brinjal", "Coconut", "Orange", "Apple",
                   "Grapes", "Rose(Loose)", "Marigold(Loose)", "Water Melon", "Papaya"],
    "storage": ["Arecanut(Betelnut/Supari)", "Cashewnuts", "Copra"],
    "cereals": ["Rice", "Wheat", "Maize"],
    "pulses": ["Gram", "Arhar/Tur", "Moong", "Urad"],
    "oilseeds": ["Groundnut", "Soybean", "Mustard", "Sunflower", "Sesamum"],
    "spices": ["Turmeric", "Chilli", "Cumin", "Coriander", "Pepper", "Cardamom"],
}

MARKET_TO_WEATHER = {
    "Mapusa": "Mapusa",
    "Pernem": "Pernem",
    "Sanquelim": "Sanquelim",
    "Valpol": "Valpol",
    "Goa State Horticultural Corporation Ltd.": "Goa State Horticultural Corporation Ltd.",
    "Canacona": "Canacona",
    "Curchorem": "South Goa",
    "Margao": "South Goa",
    "Ponda": "South Goa",
}

# ─── Lazy asset loading ──────────────────────────────────────────────────
_state: Dict[str, object] = {"loaded": False, "error": None,
                             "model": None, "feature_cols": None,
                             "encoders": None, "df_full": None,
                             "df_history": None, "weather_source": "Synthetic"}


def _load():
    if _state["loaded"] or _state["error"]:
        return
    try:
        artifacts = joblib.load(MODEL_DIR / "goa_xgb_model.pkl")
        _state["model"] = artifacts["model"]
        _state["feature_cols"] = artifacts["feature_cols"]
        _state["encoders"] = artifacts["encoders"]

        hist = pd.read_parquet(DATA_DIR / "goa_merged_historical.parquet")
        hist["arrival_date"] = pd.to_datetime(hist["arrival_date"])

        # Filter APMC duplicates and per-group price outliers (as in api_v3)
        hist = hist[~hist["market"].str.contains("APMC", case=False)].copy()
        cleaned = []
        for (_c, _m), group in hist.groupby(["commodity", "market"]):
            q01 = group["modal_price"].quantile(0.01)
            q99 = group["modal_price"].quantile(0.99)
            cleaned.append(group[(group["modal_price"] >= q01) & (group["modal_price"] <= q99)])
        hist = pd.concat(cleaned, ignore_index=True)

        hist = hist.sort_values(GROUP_COLS + ["arrival_date"]).reset_index(drop=True)
        if "arrival_tonnes" not in hist.columns:
            hist["arrival_tonnes"] = 100
        _state["df_history"] = hist

        # Weather cache (optional)
        wdfs = []
        try:
            for wf in WEATHER_CACHE.glob("*.parquet"):
                if wf.name.startswith("goa_all"):
                    continue
                w = pd.read_parquet(wf)
                w["date"] = pd.to_datetime(w["date"])
                wdfs.append(w)
        except Exception:
            wdfs = []
        if wdfs:
            _state["weather"] = pd.concat(wdfs, ignore_index=True).sort_values(["location", "date"])
            _state["weather_source"] = "Open-Meteo ERA5"
        else:
            _state["weather"] = pd.DataFrame()

        _state["df_full"] = prepare_features(hist.copy())
        _state["loaded"] = True
        print(f"✅ price engine ready: {len(hist):,} rows, "
              f"{len(_state['feature_cols'])} features, weather={_state['weather_source']}")
    except Exception as e:  # noqa: BLE001
        _state["error"] = str(e)
        print(f"⚠️ price engine failed to load: {e}")


def model_loaded() -> bool:
    _load()
    return _state["loaded"]


def load_error() -> Optional[str]:
    _load()
    return _state["error"]


# ─── Feature engineering (mirrors api_v3.py) ─────────────────────────────
def get_real_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    weather = _state.get("weather")
    if weather is None or weather.empty:
        return df

    df = df.copy()
    df["weather_location"] = df["market"].map(MARKET_TO_WEATHER)
    unmapped = df["weather_location"].isna()
    if unmapped.any():
        district_map = {"North Goa": "Mapusa", "South Goa": "South Goa"}
        df.loc[unmapped, "weather_location"] = df.loc[unmapped, "district"].map(district_map)

    df["date"] = df["arrival_date"].dt.date
    wdf = weather.copy()
    wdf["date"] = wdf["date"].dt.date

    weather_cols = ["location", "date", "temperature_2m_max", "temperature_2m_min",
                    "temperature_2m_mean", "precipitation_sum", "rain_sum",
                    "relative_humidity_2m_mean", "relative_humidity_2m_max",
                    "relative_humidity_2m_min", "wind_speed_10m_max",
                    "shortwave_radiation_sum", "et0_fao_evapotranspiration",
                    "soil_temperature_0_to_7cm_mean", "soil_moisture_0_to_7cm_mean"]
    available = [c for c in weather_cols if c in wdf.columns]
    wdf = wdf[available].rename(columns={"location": "weather_location"})

    df = df.merge(wdf, on=["weather_location", "date"], how="left")

    # Normalise both cache schemas (processed short names / raw API names)
    df = df.rename(columns={
        "temp_max": "temp_max_est", "temperature_2m_max": "temp_max_est",
        "temp_min": "temp_min_est", "temperature_2m_min": "temp_min_est",
        "temp_avg": "temp_avg_est", "temperature_2m_mean": "temp_avg_est",
        "precipitation": "rainfall_est", "precipitation_sum": "rainfall_est",
        "rain_sum": "rainfall_est",
        "humidity_avg": "humidity_est", "relative_humidity_2m_mean": "humidity_est",
    })
    if "temp_max_est" not in df.columns or df["temp_max_est"].isna().all():
        return df  # no real weather matched -> caller falls back to synthetic

    if "temp_min_est" in df.columns:
        df["temp_range_est"] = df["temp_max_est"] - df["temp_min_est"]

    # Stress flags computed on real series (never scalar defaults)
    df["heat_stress"] = (df["temp_max_est"] > 35).astype(int)
    if "temp_min_est" in df.columns:
        df["cold_stress"] = (df["temp_min_est"] < 18).astype(int)
    if "rainfall_est" in df.columns:
        df["drought_stress"] = ((df["rainfall_est"] < 5) & ~df["month"].isin(MONSOON_MONTHS)).astype(int)
        df["flood_risk"] = (df["rainfall_est"] > 100).astype(int)
    if "humidity_est" in df.columns:
        df["high_humidity"] = (df["humidity_est"] > 85).astype(int)
        df["low_humidity"] = (df["humidity_est"] < 55).astype(int)

    # Weather rolling means — named without the _est suffix to match the
    # model's feature list (rainfall_ma7, humidity_ma30, ...)
    for window in [7, 30]:
        for col in ["rainfall_est", "humidity_est", "temp_avg_est"]:
            if col in df.columns:
                df[f"{col.replace('_est', '')}_ma{window}"] = \
                    df.groupby(GROUP_COLS)[col].transform(
                        lambda x: x.rolling(window, min_periods=1).mean())

    return df.drop(columns=["weather_location", "date"], errors="ignore")


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dt = df["arrival_date"]
    df["year"] = dt.dt.year
    df["month"] = dt.dt.month
    df["day"] = dt.dt.day
    df["day_of_week"] = dt.dt.dayofweek
    df["day_of_year"] = dt.dt.dayofyear
    df["week_of_year"] = dt.dt.isocalendar().week
    df["quarter"] = dt.dt.quarter
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

    def get_season(m):
        if m in MONSOON_MONTHS:
            return "Monsoon_Kharif"
        elif m in POST_MONSOON_MONTHS:
            return "Post_Monsoon_Harvest"
        elif m in WINTER_MONTHS:
            return "Winter_Rabi"
        return "Summer_Zaid"

    df["season"] = df["month"].apply(get_season)
    df["is_monsoon"] = df["month"].isin(MONSOON_MONTHS).astype(int)
    df["is_post_monsoon"] = df["month"].isin(POST_MONSOON_MONTHS).astype(int)
    df["is_winter"] = df["month"].isin(WINTER_MONTHS).astype(int)
    df["is_summer"] = df["month"].isin(SUMMER_MONTHS).astype(int)

    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["day_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365)
    df["day_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365)

    for fest, (sm, sd, em, ed) in GOA_FESTIVALS.items():
        mask = ((df["month"] > sm) | ((df["month"] == sm) & (df["day"] >= sd))) & \
               ((df["month"] < em) | ((df["month"] == em) & (df["day"] <= ed)))
        df[f"is_{fest}"] = mask.astype(int)

    df["festival_intensity"] = sum(df[f"is_{f}"] for f in GOA_FESTIVALS)
    df["is_kharif_harvest"] = df["month"].isin([10, 11, 12]).astype(int)
    df["is_rabi_harvest"] = df["month"].isin([3, 4, 5]).astype(int)
    return df


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = add_calendar_features(df)  # month column needed by weather stress flags
    df = get_real_weather_features(df)

    has_real = "temp_max_est" in df.columns and df["temp_max_est"].notna().any()
    if has_real:
        return df

    # Synthetic fallback for Goa's coastal tropical climate
    def temp_max(m):
        base = 33
        if m in SUMMER_MONTHS: return base + 3
        elif m in MONSOON_MONTHS: return base - 2
        elif m in WINTER_MONTHS: return base - 4
        return base

    def temp_min(m):
        base = 22
        if m in WINTER_MONTHS: return base - 3
        elif m in MONSOON_MONTHS: return base + 2
        return base

    def rainfall(m):
        if m in MONSOON_MONTHS:
            return np.random.gamma(2, 400) if m in [7, 8] else np.random.gamma(2, 200)
        elif m in POST_MONSOON_MONTHS:
            return np.random.exponential(50)
        return np.random.exponential(5)

    def humidity(m):
        base = 75
        if m in MONSOON_MONTHS: return np.clip(base + np.random.normal(0, 5), 80, 95)
        elif m in POST_MONSOON_MONTHS: return np.clip(base + np.random.normal(0, 8), 70, 85)
        elif m in WINTER_MONTHS: return np.clip(base + np.random.normal(0, 10), 55, 75)
        return np.clip(base + np.random.normal(0, 10), 60, 80)

    df["temp_max_est"] = df["month"].apply(temp_max)
    df["temp_min_est"] = df["month"].apply(temp_min)
    df["temp_avg_est"] = (df["temp_max_est"] + df["temp_min_est"]) / 2
    df["temp_range_est"] = df["temp_max_est"] - df["temp_min_est"]
    df["rainfall_est"] = df["month"].apply(rainfall)
    df["humidity_est"] = df["month"].apply(humidity)

    df["heat_stress"] = (df["temp_max_est"] > 35).astype(int)
    df["cold_stress"] = (df["temp_min_est"] < 18).astype(int)
    df["drought_stress"] = ((df["rainfall_est"] < 10) & ~df["month"].isin(MONSOON_MONTHS)).astype(int)
    df["flood_risk"] = (df["rainfall_est"] > 100).astype(int)

    for window in [7, 30]:
        for col in ["rainfall_est", "humidity_est", "temp_avg_est"]:
            df[f"{col.replace('_est', '')}_ma{window}"] = df.groupby(GROUP_COLS)[col].transform(
                lambda x: x.rolling(window, min_periods=1).mean())
    return df


def add_lag_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(GROUP_COLS + ["arrival_date"]).reset_index(drop=True)

    target = "modal_price"
    arrival = "arrival_tonnes"

    for lag in [1, 2, 3, 7, 14, 30]:
        df[f"price_lag_{lag}"] = df.groupby(GROUP_COLS)[target].shift(lag)

    for window in [3, 7, 14, 30]:
        df[f"price_ma_{window}"] = df.groupby(GROUP_COLS)[target].transform(
            lambda x: x.rolling(window, min_periods=1).mean())
        df[f"price_std_{window}"] = df.groupby(GROUP_COLS)[target].transform(
            lambda x: x.rolling(window, min_periods=2).std())
        df[f"price_min_{window}"] = df.groupby(GROUP_COLS)[target].transform(
            lambda x: x.rolling(window, min_periods=1).min())
        df[f"price_max_{window}"] = df.groupby(GROUP_COLS)[target].transform(
            lambda x: x.rolling(window, min_periods=1).max())
        df[f"price_momentum_{window}"] = df[f"price_ma_{window}"] / (df[f"price_lag_{window}"] + 1) - 1
        df[f"price_cv_{window}"] = df[f"price_std_{window}"] / (df[f"price_ma_{window}"] + 1)

    for lag in [1, 7, 14]:
        df[f"price_change_{lag}d"] = df.groupby(GROUP_COLS)[target].pct_change(lag)

    for lag in [1, 7, 14]:
        df[f"arrival_lag_{lag}"] = df.groupby(GROUP_COLS)[arrival].shift(lag)

    for window in [7, 14, 30]:
        df[f"arrival_ma_{window}"] = df.groupby(GROUP_COLS)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).mean())
        df[f"arrival_sum_{window}"] = df.groupby(GROUP_COLS)[arrival].transform(
            lambda x: x.rolling(window, min_periods=1).sum())

    df["supply_pressure"] = df[arrival] / (df["arrival_ma_30"] + 1)
    df["supply_pressure_7d"] = df[arrival] / (df["arrival_ma_7"] + 1)
    df["price_spread"] = df["max_price"] - df["min_price"]
    df["price_spread_pct"] = df["price_spread"] / (df["modal_price"] + 1)
    return df


def add_commodity_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for cat, items in COMMODITY_CATEGORIES.items():
        df[f"is_{cat}"] = df["commodity"].isin(items).astype(int)
    df["perishability_score"] = df["is_perishable"] * 2 + df["is_storage"] * (-1)
    df["cereal_kharif"] = (df["is_cereals"] & df["month"].isin([6, 7, 8, 9, 10])).astype(int)
    df["cereal_rabi"] = (df["is_cereals"] & df["month"].isin([11, 12, 1, 2, 3, 4])).astype(int)
    df["pulse_kharif"] = (df["is_pulses"] & df["month"].isin([6, 7, 8, 9])).astype(int)
    df["pulse_rabi"] = (df["is_pulses"] & df["month"].isin([10, 11, 12, 1, 2, 3])).astype(int)
    return df


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    encoders = _state["encoders"] or {}
    for col in ["district", "commodity", "variety", "grade", "market", "season"]:
        if col not in df.columns:
            continue
        le = encoders.get(col)
        if le is not None:
            known = set(le.classes_.astype(str))
            df[col] = df[col].astype(str).apply(lambda x: x if x in known else "Unknown")
            df[f"{col}_enc"] = le.transform(df[col])
        else:
            df[f"{col}_enc"] = 0
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_weather_features(df)  # includes calendar features
    df = add_lag_rolling_features(df)
    df = add_commodity_features(df)
    df = encode_categoricals(df)
    return df


# ─── Public API ──────────────────────────────────────────────────────────
def _norm(s) -> str:
    """Tolerant name normalisation: lowercase, collapse spaces, drop stray parens."""
    s = str(s).strip().lower().replace("(", " ").replace(")", " ")
    return " ".join(s.split())


def _norm_col(col):
    """Elementwise _norm for a Series; passthrough for scalars."""
    if isinstance(col, pd.Series):
        return col.astype(str).map(_norm)
    return _norm(col)


def _filter(df: pd.DataFrame, district=None, commodity=None, market=None) -> pd.DataFrame:
    if district and str(district).lower() != "all":
        df = df[_norm_col(df["district"]) == _norm(district)]
    if commodity:
        df = df[_norm_col(df["commodity"]) == _norm(commodity)]
    if market and str(market).lower() != "all":
        df = df[_norm_col(df["market"]) == _norm(market)]
    return df


def predict_14d(district=None, commodity=None, market=None) -> List[Dict]:
    """14-day predictions for every commodity-market matching the filters."""
    _load()
    if not _state["loaded"]:
        raise RuntimeError(f"price engine unavailable: {_state['error']}")

    latest = _state["df_full"].groupby(GROUP_COLS, sort=False).tail(1).copy()
    latest = _filter(latest, district, commodity, market)
    if latest.empty:
        raise LookupError("No data for the selected district/commodity/market")

    model = _state["model"]
    feature_cols = _state["feature_cols"]
    for col in feature_cols:
        if col not in latest.columns:
            latest[col] = 0
    latest = latest.loc[:, ~latest.columns.duplicated()]

    pred_pct = model.predict(latest[feature_cols])
    latest["predicted_price_14d"] = latest["modal_price"].values * (1 + pred_pct)
    latest["predicted_change_pct"] = (pred_pct * 100).round(2)

    out = []
    for _, row in latest.sort_values(["commodity", "market"]).iterrows():
        out.append({
            "district": row["district"],
            "commodity": row["commodity"],
            "market": row["market"],
            "current_price": round(float(row["modal_price"]), 2),
            "predicted_price_14d": round(float(row["predicted_price_14d"]), 2),
            "predicted_change_pct": float(row["predicted_change_pct"]),
            "prediction_date": datetime.now().strftime("%Y-%m-%d"),
            "model": "XGBoost",
            "weather_source": _state["weather_source"],
        })
    return out


def trajectory(district=None, commodity=None, market=None, days: int = 14) -> List[Dict]:
    """Day-by-day trajectory per matching commodity-market."""
    _load()
    if not _state["loaded"]:
        raise RuntimeError(f"price engine unavailable: {_state['error']}")

    days = max(3, min(int(days or 14), 30))
    df_full = _state["df_full"]
    latest = df_full.groupby(GROUP_COLS, sort=False).tail(1).copy()
    latest = _filter(latest, district, commodity, market)
    if latest.empty:
        raise LookupError("No data for the selected district/commodity/market")

    model = _state["model"]
    feature_cols = _state["feature_cols"]

    results = []
    for _, row in latest.iterrows():
        group = df_full[
            (df_full["district"] == row["district"]) &
            (df_full["commodity"] == row["commodity"]) &
            (df_full["market"] == row["market"])
        ].tail(1)
        if group.empty:
            continue

        feats = group[feature_cols].values.flatten().reshape(1, -1)
        pred = float(model.predict(feats)[0])

        current_price = float(row["modal_price"])
        anchor_price = float(row["modal_price"])
        # Anchor the forecast calendar at the latest known data, but never
        # label it in the past (features still come from the last known row).
        base_date = max(row["arrival_date"], pd.Timestamp.now().normalize())
        traj = []
        for day in range(1, days + 1):
            pred_price = current_price * (1 + pred)
            traj.append({
                "day_ahead": day,
                "day": day,
                "date": (base_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "predicted_price": round(pred_price, 2),
                "change_from_current_pct": round((pred_price - anchor_price) /
                                                 anchor_price * 100, 2),
                "change_from_prev_pct": round(pred * 100, 2),
                "change_from_initial_pct": round((pred_price - anchor_price) /
                                                 anchor_price * 100, 2),
            })
            current_price = pred_price

        results.append({
            "district": row["district"],
            "commodity": row["commodity"],
            "market": row["market"],
            "current_price": round(float(row["modal_price"]), 2),
            "trajectory": traj,
        })
    return results


def single(district: str, commodity: str, market: str) -> Dict:
    _load()
    if not _state["loaded"]:
        raise RuntimeError(f"price engine unavailable: {_state['error']}")

    df_full = _state["df_full"]
    latest = df_full.groupby(GROUP_COLS, sort=False).tail(1).copy()
    match = latest[(_norm_col(latest["district"]) == _norm(district)) &
                   (_norm_col(latest["commodity"]) == _norm(commodity)) &
                   (_norm_col(latest["market"]) == _norm(market))]
    if match.empty:
        # fall back to any market in the district
        match = latest[(_norm_col(latest["district"]) == _norm(district)) &
                       (_norm_col(latest["commodity"]) == _norm(commodity))]
    if match.empty:
        raise LookupError(f"No data for {commodity} in {district}")

    row = match.iloc[0]
    month = datetime.now().month
    season = ("Monsoon_Kharif" if month in MONSOON_MONTHS else
              "Post_Monsoon" if month in POST_MONSOON_MONTHS else
              "Winter_Rabi" if month in WINTER_MONTHS else "Summer_Zaid")
    supply = "High" if float(row.get("supply_pressure", 1)) > 1.2 else "Normal"

    preds = predict_14d(district, commodity, market)
    p = preds[0]
    return {
        **p,
        "market": row["market"],
        "confidence": 0.88,
        "factors": {
            "season": season,
            "supply_pressure": supply,
            "weather_impact": "Monsoon" if month in MONSOON_MONTHS else "Dry",
            "festival_nearby": bool(any(row.get(f"is_{f}", 0) for f in GOA_FESTIVALS)),
        },
    }


def known_commodities() -> List[str]:
    _load()
    if not _state["loaded"]:
        return []
    return sorted(_state["df_history"]["commodity"].unique().tolist())


def known_markets() -> List[Dict[str, str]]:
    _load()
    if not _state["loaded"]:
        return []
    df = _state["df_history"][["district", "market"]].drop_duplicates()
    return [{"district": r["district"], "market": r["market"]}
            for _, r in df.sort_values(["district", "market"]).iterrows()]
