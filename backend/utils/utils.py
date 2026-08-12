import os
import pandas as pd
import numpy as np
import joblib
import json
import requests
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from geopy.geocoders import Nominatim
    HAVE_GEOPY = True
except Exception:
    Nominatim = None
    HAVE_GEOPY = False

try:
    import ee
    HAVE_EE = True
except Exception:
    ee = None
    HAVE_EE = False

try:
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import StandardScaler
except Exception:
    cosine_similarity = None
    StandardScaler = None

# ------------------ INIT ------------------

geolocator = Nominatim(user_agent="crop_app") if HAVE_GEOPY else None

if HAVE_EE:
    try:
        ee.Initialize(project='crop-suitability-project')
    except Exception:
        pass

# ------------------ LOAD MODEL (optional; guarded)
model = None
le = None
district_crop_map = {}
historical_lookup = {}
try:
    model_path = os.path.join(BASE_DIR, 'final_model', 'rf_model.pkl')
    le_path = os.path.join(BASE_DIR, 'final_model', 'label_encoder.pkl')
    district_crop_map_path = os.path.join(BASE_DIR, 'final_model', 'district_crop_map.json')
    historical_lookup_path = os.path.join(BASE_DIR, 'final_model', 'historical_lookup.json')

    if os.path.exists(model_path):
        model = joblib.load(model_path)
    if os.path.exists(le_path):
        le = joblib.load(le_path)
    if os.path.exists(district_crop_map_path):
        with open(district_crop_map_path) as f:
            district_crop_map = json.load(f)
    if os.path.exists(historical_lookup_path):
        with open(historical_lookup_path) as f:
            historical_lookup = json.load(f)
except Exception:
    model = None
    le = None
    district_crop_map = {}
    historical_lookup = {}

# ------------------ CROP ROTATION DATA (optional)
try:
    excel_path = os.path.join(BASE_DIR, '..', 'FarmIntel_crop_master_v3_FIXED.xlsx')
    crop_rotation_df = pd.read_excel(excel_path, engine='openpyxl')
except ImportError:
    print('Openpyxl is not installed; crop rotation dataset cannot be loaded.')
    crop_rotation_df = pd.DataFrame()
except Exception as e:
    print(f'Failed to load crop rotation dataset: {e}')
    crop_rotation_df = pd.DataFrame()

# ------------------ FERTILIZER DATA (optional)
try:
    fertilizer_df = pd.read_csv(os.path.join(BASE_DIR, '..', 'fertilizer_recommendation_dataset.csv'))
    fertilizer_df["Crop"] = fertilizer_df["Crop"].str.lower()
    fertilizer_df["Soil"] = fertilizer_df["Soil"].str.lower()
    fertilizer_features = ["Nitrogen", "Phosphorous", "Potassium", "PH"]
    if StandardScaler is not None:
        fertilizer_scaler = StandardScaler()
        fertilizer_scaled = fertilizer_scaler.fit_transform(fertilizer_df[fertilizer_features])
    else:
        fertilizer_scaler = None
        fertilizer_scaled = None
except Exception:
    fertilizer_df = pd.DataFrame()
    fertilizer_features = ["Nitrogen", "Phosphorous", "Potassium", "PH"]
    fertilizer_scaler = None
    fertilizer_scaled = None

# ------------------ LOCATION FALLBACKS ------------------
DISTRICT_COORDS = {
    "north goa": (15.5, 73.8),
    "south goa": (15.2, 74.0),
    "nashik": (20.0, 73.8),
    "lasalgaon": (20.1, 74.1),
    "pune": (18.5, 73.9),
    "nagpur": (21.1, 79.1),
    "bangalore": (12.9, 77.6),
    "mysore": (12.3, 76.6),
    "ludhiana": (30.9, 75.9),
    "amritsar": (31.6, 74.9),
    "patiala": (30.3, 76.4),
    "bhopal": (23.3, 77.4),
    "indore": (22.7, 75.9),
    "ujjain": (23.2, 75.8),
    "vijayawada": (16.5, 80.6),
    "guntur": (16.3, 80.4),
    "kurnool": (15.8, 78.0),
}

# ------------------ LOCATION ------------------

def get_district(lat, lon):
    if geolocator is not None:
        try:
            location = geolocator.reverse((lat, lon), language='en')
            if location is None:
                return None
            address = location.raw.get('address', {})
            district = (
                address.get('state_district') or
                address.get('county') or
                address.get('district') or
                address.get('city')
            )
            if district:
                return district.lower().replace(" district", "").strip()
        except Exception:
            pass

    # Fallback: return nearest district by simple rounding using DISTRICT_COORDS
    try:
        best = None
        best_dist = float('inf')
        for d, (lat0, lon0) in DISTRICT_COORDS.items():
            dist = (lat - lat0) ** 2 + (lon - lon0) ** 2
            if dist < best_dist:
                best_dist = dist
                best = d
        return best
    except Exception:
        return None


def get_lat_lon_from_district(district):
    if not district:
        return None, None

    if geolocator is not None:
        try:
            location = geolocator.geocode(f"{district}, India")
            if location:
                return location.latitude, location.longitude
        except Exception:
            pass

    # Fallback: lookup in DISTRICT_COORDS
    try:
        return DISTRICT_COORDS.get(district.lower(), (None, None))
    except Exception:
        return None, None

# ------------------ NDVI ------------------

def get_season_dates(season):
    season = season.lower()

    if season == "kharif":
        return '2025-06-01', '2025-10-31'
    elif season == "rabi":
        return '2025-10-01', '2026-03-31'
    else:
        return '2025-01-01', '2025-12-31'


def mask_s2_clouds(img):
    qa = img.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11

    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
           qa.bitwiseAnd(cirrus_bit_mask).eq(0))

    return img.updateMask(mask)


def get_ndvi(lat, lon, season):

    start, end = get_season_dates(season)
    region = ee.Geometry.Point([lon, lat]).buffer(500)

    col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(region)
           .filterDate(start, end)
           .map(mask_s2_clouds))

    def add_ndvi(img):
        nd = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return img.addBands(nd)

    col = col.map(add_ndvi)

    ndvi_max = col.select('NDVI').max()

    stats = ndvi_max.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=10,
        bestEffort=True
    ).getInfo()

    return stats.get('NDVI', 0.3)


def land_suitability(lat, lon, season):
    ndvi = get_ndvi(lat, lon, season)

    if ndvi > 0.5:
        return "Highly Suitable", ndvi
    elif ndvi > 0.25:
        return "Moderately Suitable", ndvi
    else:
        return "Low Suitable", ndvi

# ------------------ WEATHER ------------------

def get_weather(lat, lon):

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=relativehumidity_2m,precipitation"

    data = requests.get(url).json()

    temp = data['current_weather']['temperature']
    current_time = data['current_weather']['time']

    hourly_times = data['hourly']['time']

    idx = min(
        range(len(hourly_times)),
        key=lambda i: abs(pd.to_datetime(hourly_times[i]) - pd.to_datetime(current_time))
    )

    humidity = data['hourly']['relativehumidity_2m'][idx]
    rainfall = data['hourly']['precipitation'][idx]

    return temp, humidity, rainfall


def get_weather_forecast(lat, lon, days=14):
    """Get 14-day weather forecast from Open-Meteo."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max&forecast_days={days}&timezone=Asia/Kolkata"
    
    try:
        data = requests.get(url, timeout=10).json()
        daily = data.get('daily', {})
        return [
            {
                'date': daily['time'][i],
                'temp_max': daily['temperature_2m_max'][i],
                'temp_min': daily['temperature_2m_min'][i],
                'precipitation': daily['precipitation_sum'][i],
                'humidity': daily['relative_humidity_2m_max'][i],
            }
            for i in range(len(daily.get('time', [])))
        ]
    except Exception as e:
        print(f"Weather forecast error: {e}")
        return []

# ------------------ CROP ROTATION ------------------

def get_rotation_suggestions(prev_crop, N, P, K, top_n=3):
    """
    Given the previous crop and current soil NPK, returns ranked
    suggestions for the next crop to plant.
    """

    if crop_rotation_df.empty:
        return {"error": "Rotation dataset unavailable. Please install openpyxl and ensure FarmIntel_crop_master_v3_FIXED.xlsx is present."}

    if 'crop' not in crop_rotation_df.columns:
        return {"error": "Rotation dataset missing required 'crop' column."}

    # 1. Find prev crop in master
    match = crop_rotation_df[crop_rotation_df['crop'].str.lower() == prev_crop.strip().lower()]
    if match.empty:
        available = crop_rotation_df['crop'].tolist()
        return {"error": f"Crop '{prev_crop}' not found. Available: {available}"}

    row = match.iloc[0]

    # 2. Compute depleted soil
    N_after = max(0, N - row['N_loss'])
    P_after = max(0, P - row['P_loss'])
    K_after = max(0, K - row['K_loss'])

    depleted = np.array([N_after, P_after, K_after], dtype=float)

    # 3. Get candidate next crops
    candidates = [c.strip() for c in str(row['best_next_crops']).split(';')]

    # 4. Score each candidate
    results = []
    for crop_name in candidates:
        cand = crop_rotation_df[crop_rotation_df['crop'] == crop_name]
        if cand.empty:
            cand = crop_rotation_df[crop_rotation_df['crop'].str.lower() == crop_name.lower()]
        if cand.empty:
            continue

        cand_row = cand.iloc[0]
        ideal = cand_row[['N', 'P', 'K']].values.astype(float)

        # Cosine similarity between depleted soil and crop's ideal NPK
        if depleted.sum() == 0:
            cos_score = 0.0
        else:
            cos_score = cosine_similarity(
                depleted.reshape(1, -1),
                ideal.reshape(1, -1)
            )[0][0]

        # Nitrogen-fixing bonus (+0.05 if N is low after harvest)
        n_fix = cand_row['nitrogen_fixing'] == 'Yes'
        n_fix_bonus = 0.05 if (n_fix and N_after < 40) else 0.0

        final_score = cos_score + n_fix_bonus

        # Nutrient gap (how much fertiliser needed)
        n_gap = max(0, ideal[0] - N_after)
        p_gap = max(0, ideal[1] - P_after)
        k_gap = max(0, ideal[2] - K_after)

        results.append({
            'crop': cand_row['crop'],
            'family': cand_row['family'],
            'season': cand_row['season'],
            'cosine_score': float(round(cos_score, 4)),
            'n_fix_bonus': float(round(n_fix_bonus, 4)),
            'final_score': float(round(final_score, 4)),
            'nitrogen_fixing': n_fix,
            'N_gap': float(round(n_gap, 1)),
            'P_gap': float(round(p_gap, 1)),
            'K_gap': float(round(k_gap, 1)),
            'soil_type': cand_row['soil_type'],
            'ph_range': f"{cand_row['ph_min']} - {cand_row['ph_max']}",
            'temp_range': f"{cand_row['temp_min']} - {cand_row['temp_max']}°C",
        })

    results.sort(key=lambda x: x['final_score'], reverse=True)

    # 5. Warnings
    warnings_list = []
    if N_after < 20:
        warnings_list.append("Nitrogen critically low — prioritise nitrogen-fixing crop or add urea")
    if P_after < 10:
        warnings_list.append("Phosphorus very low — add DAP/SSP before next sowing")
    if K_after < 10:
        warnings_list.append("Potassium low — apply MOP before next season")

    return {
        'season1_crop': row['crop'],
        'depleted_soil': {'N': float(N_after), 'P': float(P_after), 'K': float(K_after)},
        'suggestions': results[:top_n],
        'warnings': warnings_list,
        'all_candidates': results
    }


def plan_two_season_rotation(
    season1_crop,
    N=None,
    P=None,
    K=None,
    ph=None,
    lat=None,
    lon=None,
    district=None,
    mode="auto",
    top_n=3
):
    """
    Generates a full 2-season rotation plan.
    Season 1 = provided crop.
    Season 2 = best match from rotation engine.
    Also shows what Season 3 would look like.
    Supports auto-fetching NPK/pH from location if not provided.
    """

    # Auto-fetch NPK/pH from location if not provided
    if N is None or P is None or K is None or ph is None:
        location_data = get_default_npk_from_location(lat=lat, lon=lon, district=district, mode=mode)
        N = N if N is not None else location_data.get("N", 90)
        P = P if P is not None else location_data.get("P", 40)
        K = K if K is not None else location_data.get("K", 40)
        ph = ph if ph is not None else location_data.get("ph", 6.5)

    # Season 2
    result_s2 = get_rotation_suggestions(season1_crop, N, P, K, top_n=top_n)
    if 'error' in result_s2:
        return {"error": result_s2['error']}

    best_s2 = result_s2['suggestions'][0]
    s2_soil = result_s2['depleted_soil']

    # Season 3 preview
    result_s3 = get_rotation_suggestions(
        best_s2['crop'],
        s2_soil['N'], s2_soil['P'], s2_soil['K'],
        top_n=2
    )

    s3_name = result_s3['suggestions'][0]['crop'] if result_s3.get('suggestions') else 'TBD'
    s3_soil = result_s3['depleted_soil']

    return {
        'season1': season1_crop,
        'season2_options': result_s2['suggestions'],
        'season2_best': best_s2['crop'],
        'season3_preview': s3_name,
        'soil_after_s1': {k: float(v) for k, v in s2_soil.items()},
        'soil_after_s2': {k: float(v) for k, v in s3_soil.items()},
        'warnings': result_s2['warnings'],
        'input_npk': {k: float(v) for k, v in {'N': N, 'P': P, 'K': K, 'ph': ph}.items()}
    }

# ------------------ FERTILIZER RECOMMENDATION ------------------

def recommend_fertilizer(crop, soil, n, p, k, ph, top_k=5):
    crop = crop.lower()
    soil = soil.lower()

    crop_df = fertilizer_df[fertilizer_df["Crop"] == crop]

    if len(crop_df) == 0:
        return None

    crop_scaled = fertilizer_scaler.transform(crop_df[fertilizer_features])

    user_input = pd.DataFrame([[n, p, k, ph]], columns=fertilizer_features)
    user_vector = fertilizer_scaler.transform(user_input)

    similarities = cosine_similarity(user_vector, crop_scaled)[0]

    crop_df = crop_df.copy()
    crop_df["Similarity"] = similarities

    result = crop_df.sort_values(by="Similarity", ascending=False)

    return result.head(top_k)

# ------------------ MAIN SYSTEM (Crop Recommendation) ------------------

def full_system(
    lat=None,
    lon=None,
    district=None,
    season="kharif",
    mode="auto",
    N=None,
    P=None,
    K=None
):

    # LOCATION
    if mode == "auto":
        lat, lon = get_lat_lon_from_district(district)
        district = district.lower()

    elif mode == "coords":
        district = get_district(lat, lon)

    if lat is None or lon is None or district is None:
        return {"error": "Invalid location input"}

    # DEFAULT NPK
    if N is None: N = 90
    if P is None: P = 40
    if K is None: K = 40

    # NDVI
    try:
        suitability, ndvi = land_suitability(lat, lon, season)
    except:
        suitability, ndvi = "Moderately Suitable", 0.5

    # WEATHER
    try:
        temp, humidity, rainfall = get_weather(lat, lon)
    except:
        temp, humidity, rainfall = 25, 70, 200

    # MODEL INPUT
    input_df = pd.DataFrame([{
        'N': N,
        'P': P,
        'K': K,
        'temperature': temp,
        'humidity': humidity,
        'ph': 6.5,
        'rainfall': rainfall
    }])

    if model is None or le is None:
        # Fallback to district crop map if the prediction model is unavailable
        allowed = district_crop_map.get(district, {}).get(season, [])
        if allowed:
            return {
                "Suitability": suitability,
                "NDVI": round(ndvi, 2),
                "Top Crops": [(crop, 0.5) for crop in allowed[:3]]
            }
        return {
            "error": "Prediction model unavailable",
            "details": "The backend model is not loaded. Please run the server from the collab directory or ensure final_model files exist."
        }

    probs = model.predict_proba(input_df)[0]
    prob_dict = dict(zip(le.classes_, probs))

    # FALLBACK
    if district not in district_crop_map or season not in district_crop_map[district]:
        sorted_crops = sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)

        return {
            "Suitability": suitability,
            "NDVI": round(ndvi, 2),
            "Top Crops": sorted_crops[:3]
        }

    # FILTERED
    allowed = district_crop_map[district][season]

    results = []

    for crop in allowed:

        crop = crop.lower()

        agro = prob_dict.get(crop, prob_dict.get('maize', 0)*0.85)

        yield_s = historical_lookup.get(district, {}) \
            .get(season, {}) \
            .get(crop, {}) \
            .get("yield_score", 0)

        area_s = historical_lookup.get(district, {}) \
            .get(season, {}) \
            .get(crop, {}) \
            .get("area_share", 0)

        final_score = 0.5*agro + 0.3*yield_s + 0.2*area_s

        results.append((crop, final_score))

    results.sort(key=lambda x: x[1], reverse=True)

    return {
        "Suitability": suitability,
        "NDVI": round(ndvi, 2),
        "Top Crops": results[:3]
    }


# ------------------ LOCATION-BASED DEFAULT NPK ------------------

def get_default_npk_from_location(lat=None, lon=None, district=None, mode="auto"):
    """
    Get default NPK values based on location.
    Uses weather data and district-based historical averages as fallback.
    """
    
    # LOCATION
    if mode == "auto" and district:
        lat, lon = get_lat_lon_from_district(district)
        district = district.lower()
    elif mode == "coords" and lat and lon:
        district = get_district(lat, lon)
    
    if lat is None or lon is None or district is None:
        # Return default values if location resolution fails
        return {"N": 90, "P": 40, "K": 40, "ph": 6.5, "rainfall": 200, "temperature": 25}
    
    # Try to get weather data for more accurate defaults
    try:
        temp, humidity, rainfall = get_weather(lat, lon)
    except:
        temp, humidity, rainfall = 25, 70, 200
    
    # Use district-based historical averages if available, otherwise use defaults
    # These are reasonable defaults for Indian agricultural regions
    # Could be enhanced with actual soil database lookups
    default_npk = {
        "N": 90,
        "P": 40,
        "K": 40,
        "ph": 6.5,
        "rainfall": round(rainfall, 1),
        "temperature": round(temp, 1)
    }
    
    # Adjust based on district if in historical_lookup
    if district in historical_lookup:
        # Use first available season's data as rough average
        for season_data in historical_lookup[district].values():
            if isinstance(season_data, dict):
                # Get average yield/area data to infer soil fertility
                pass
    
    return default_npk