import os
import threading
import time

import pandas as pd
import numpy as np
import joblib
import json
import requests
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _first_existing(*paths):
    """First path that exists — datasets ship beside the backend or one level
    up depending on how the repo was checked out."""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]

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
    # BASE_DIR is backend/utils, so the shared artifacts live one level up.
    # Without the '../models' candidate this module silently loaded nothing
    # and every caller (rotation history, legacy full_system) saw empty maps.
    _model_dir = _first_existing(os.path.join(BASE_DIR, 'models'),
                                 os.path.join(BASE_DIR, '..', 'models'),
                                 os.path.join(BASE_DIR, 'final_model'))
    model_path = os.path.join(_model_dir, 'rf_model.pkl')
    le_path = os.path.join(_model_dir, 'label_encoder.pkl')
    district_crop_map_path = os.path.join(_model_dir, 'district_crop_map.json')
    historical_lookup_path = os.path.join(_model_dir, 'historical_lookup.json')

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
    excel_path = _first_existing(
        os.path.join(BASE_DIR, 'FarmIntel_crop_master_v3_FIXED.xlsx'),
        os.path.join(BASE_DIR, '..', 'FarmIntel_crop_master_v3_FIXED.xlsx'),
    )
    crop_rotation_df = pd.read_excel(excel_path, engine='openpyxl')
except ImportError:
    print('Openpyxl is not installed; crop rotation dataset cannot be loaded.')
    crop_rotation_df = pd.DataFrame()
except Exception as e:
    print(f'Failed to load crop rotation dataset: {e}')
    crop_rotation_df = pd.DataFrame()

# ------------------ FERTILIZER DATA (optional)
try:
    fertilizer_df = pd.read_csv(_first_existing(
        os.path.join(BASE_DIR, 'fertilizer_recommendation_dataset.csv'),
        os.path.join(BASE_DIR, '..', 'fertilizer_recommendation_dataset.csv'),
    ))
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

# Trained fertiliser classifier, when the repo has one (train_fertilizer_model.py)
try:
    _fert_model_dir = _first_existing(os.path.join(BASE_DIR, '..', 'models'),
                                      os.path.join(BASE_DIR, 'models'))
    _FERTILIZER_BUNDLE = joblib.load(
        os.path.join(_fert_model_dir, 'fertilizer_model.pkl'))
    if not (isinstance(_FERTILIZER_BUNDLE, dict)
            and _FERTILIZER_BUNDLE.get('model') is not None):
        _FERTILIZER_BUNDLE = None
except Exception:
    _FERTILIZER_BUNDLE = None

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
            location = geolocator.reverse((lat, lon), language='en', timeout=5)
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
            location = geolocator.geocode(f"{district}, India", timeout=5)
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

# Current weather changes slowly; an 800 ms provider round-trip on every
# /predict, /rotation/plan and /weather call was the single biggest latency
# item. A short TTL keyed on ~1 km coordinates keeps the card live enough
# while making repeat requests local.
_WEATHER_CACHE: dict = {}
_WEATHER_CACHE_TTL_S = 600
_WEATHER_CACHE_LOCK = threading.Lock()


def get_weather(lat, lon):
    """Current weather (temperature, humidity, rainfall) for a coordinate.

    Cached for 10 minutes per ~1 km grid cell. Raises on provider failure so
    the caller keeps control of its own fallback.
    """
    try:
        key = (round(float(lat), 2), round(float(lon), 2))
    except (TypeError, ValueError):
        key = None

    now = time.time()
    if key is not None:
        with _WEATHER_CACHE_LOCK:
            hit = _WEATHER_CACHE.get(key)
            if hit and now - hit[0] < _WEATHER_CACHE_TTL_S:
                return hit[1]

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=relativehumidity_2m,precipitation"

    data = requests.get(url, timeout=6).json()

    temp = data['current_weather']['temperature']
    current_time = data['current_weather']['time']

    hourly_times = data['hourly']['time']

    idx = min(
        range(len(hourly_times)),
        key=lambda i: abs(pd.to_datetime(hourly_times[i]) - pd.to_datetime(current_time))
    )

    humidity = data['hourly']['relativehumidity_2m'][idx]
    rainfall = data['hourly']['precipitation'][idx]

    values = (temp, humidity, rainfall)
    if key is not None:
        with _WEATHER_CACHE_LOCK:
            if len(_WEATHER_CACHE) > 500:
                _WEATHER_CACHE.clear()
            _WEATHER_CACHE[key] = (now, values)
    return values


_WEATHER_FC_CACHE: dict = {}
_WEATHER_FC_TTL_S = 1800
_WATHER_FC_LOCK = threading.Lock()


def get_weather_forecast(lat, lon, days=14):
    """Get 14-day weather forecast from Open-Meteo.

    Cached for 30 minutes per ~1 km grid cell: the factors card and the
    single-price view both need it, and a daily forecast does not change
    between two page loads. An empty result is never cached, so a transient
    provider error cannot blank the card for half an hour.
    """
    try:
        key = (round(float(lat), 2), round(float(lon), 2), int(days))
    except (TypeError, ValueError):
        key = None

    now = time.time()
    if key is not None:
        with _WATHER_FC_LOCK:
            hit = _WEATHER_FC_CACHE.get(key)
            if hit and now - hit[0] < _WEATHER_FC_TTL_S:
                return hit[1]

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max&forecast_days={days}&timezone=Asia/Kolkata"

    try:
        data = requests.get(url, timeout=10).json()
        daily = data.get('daily', {})
        out = [
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

    if out and key is not None:
        with _WATHER_FC_LOCK:
            if len(_WEATHER_FC_CACHE) > 200:
                _WEATHER_FC_CACHE.clear()
            _WEATHER_FC_CACHE[key] = (now, out)
    return out

# ------------------ CROP ROTATION ------------------

def _rotation_name(name) -> str:
    out = str(name).strip().lower()
    for ch in ('\u2013', '\u2014', '-', '_', '(', ')', '.', ','):
        out = out.replace(ch, ' ')
    return ' '.join(out.split())


# Master-xlsx crop names -> the names the district historical table uses.
# Without this the district record is looked up under "Green Gram" while the
# table stores it as "moong", and every history term silently reads zero.
_HISTORY_ALIASES = {
    "green gram": "moong", "moong": "moong", "mungbean": "moong",
    "black gram": "urad", "urad": "urad", "blackgram": "urad",
    "chickpea": "gram", "gram": "gram", "bengal gram": "gram",
    "pigeon pea": "tur", "tur": "tur", "arhar": "tur",
    "finger millet": "ragi", "ragi": "ragi",
    "pearl millet": "bajra", "bajra": "bajra",
    "sorghum": "jowar", "jowar": "jowar",
    "paddy": "rice", "rice": "rice",
    "lentil": "lentil", "masoor": "lentil",
    "small millets": "small millets", "millet": "bajra",
    "mustard": "mustard", "soybean": "soybean",
}


def _district_crop_history(district, crop_name) -> dict:
    """How well this district already grows a crop, across its seasons.

    A rotation that asks a farmer to plant something their district has no
    record of growing is a worse suggestion than one built on a crop the
    district already harvests well, so the yield/area record is folded into
    the score. Absent district (or no historical rows) contributes nothing.
    """
    if not district or not historical_lookup:
        return {"yield_score": 0.0, "area_share": 0.0}
    wanted = _rotation_name(district)
    rows = historical_lookup.get(wanted)
    if rows is None:
        for key, value in historical_lookup.items():
            if _rotation_name(key) == wanted:
                rows = value
                break
    if not rows:
        return {"yield_score": 0.0, "area_share": 0.0}
    norm = _rotation_name(crop_name)
    targets = {norm, _HISTORY_ALIASES.get(norm, norm)}
    yields, areas = [], []
    for _season, crops in (rows or {}).items():
        for name, stats in (crops or {}).items():
            if _rotation_name(name) in targets:
                yields.append(float(stats.get("yield_score") or 0.0))
                areas.append(float(stats.get("area_share") or 0.0))
    if not yields:
        return {"yield_score": 0.0, "area_share": 0.0}
    return {
        "yield_score": max(yields),
        "area_share": max(areas),
    }


_DISTRICT_CROPS_CACHE = {}


def _district_crop_sets(district, state=None):
    """(crops this district grows, crops its state grows) in master naming.

    The master table's rotation candidates are agronomic, not local: mustard
    after rice is textbook, but recommending it in Kolar asks a farmer to grow
    something the district has no record of. The crop map answers what is
    actually grown, so the ranking can be held to it.

    Both sets are returned already translated to the master table's names
    ("moong" -> "green gram"), because that is what the candidates are called.
    """
    if not district and not state:
        return set(), set()
    key = (_rotation_name(district or ""), _rotation_name(state or ""))
    if key in _DISTRICT_CROPS_CACHE:
        return _DISTRICT_CROPS_CACHE[key]

    local, state_wide = set(), set()
    try:
        import district_data as dd

        loc = dd.resolve_district(district, state) if district else None
        name = (loc or {}).get("district")
        # A district the soil survey does not cover (Kollam, Karnal) resolves
        # to nothing offline, so the caller's state is the only locality left.
        state = ((loc or {}).get("state") or _rotation_name(state or "")).lower()
        if name:
            for crops in (dd.DISTRICT_CROP_MAP.get(name) or {}).values():
                for c in (crops or []):
                    cc = _rotation_name(c)
                    if cc in dd._AGGREGATE_CATEGORIES:
                        continue
                    local.add(_HISTORY_ALIASES.get(cc, cc))
        if state:
            for dname, seasons in dd.DISTRICT_CROP_MAP.items():
                profs = dd.SOIL_PROFILE_INDEX.get(dname) or []
                if not profs or (profs[0].get("state") or "") != state:
                    continue
                for crops in (seasons or {}).values():
                    for c in (crops or []):
                        cc = _rotation_name(c)
                        if cc in dd._AGGREGATE_CATEGORIES:
                            continue
                        state_wide.add(_HISTORY_ALIASES.get(cc, cc))
        # States the government crop map does not track (Kerala, Tamil Nadu,
        # Gujarat, Haryana, West Bengal, Odisha) still have a curated list of
        # what is grown there; without it those districts fall straight through
        # to the unconstrained agronomic ranking.
        if state and not state_wide:
            for crops in (dd._STATE_FALLBACK_CROPS.get(state) or {}).values():
                for c in (crops or []):
                    cc = _rotation_name(c)
                    if cc in dd._AGGREGATE_CATEGORIES:
                        continue
                    state_wide.add(_HISTORY_ALIASES.get(cc, cc))
    except Exception as e:  # noqa: BLE001
        print(f"[rotation] district crop sets unavailable: {e}")

    state_wide |= local
    _DISTRICT_CROPS_CACHE[key] = (local, state_wide)
    return local, state_wide


def get_rotation_suggestions(prev_crop, N, P, K, top_n=3, district=None,
                            state=None):
    """
    Given the previous crop and current soil NPK, rank the next crop.

    Scoring is the NPK-fit cosine plus the things that actually decide a
    rotation and that the cosine alone ignored:

        cos            similarity of the depleted soil to the crop's ideal NPK
        history        this district's own yield/area record for the crop
        n_fix_bonus    legume after a nitrogen-hungry cereal, or when N is low
        same_family    penalty: same botanical family back-to-back shares soil
                       -borne pathogens and pests
        avoid_after    penalty: the master table says this crop performs badly
                       straight after the previous one

    Penalties are what stop gram-after-gram: the two are the same family, so
    their NPK profiles are close and the old cosine score actively preferred
    the repetition.

    Finally the list is gated on what the district actually grows, because the
    master table's candidates are agronomic rather than local. Only crops in
    the district's crop map are offered; if the district has no record for any
    candidate, the state's crops are used, and only if those are empty too does
    the unconstrained agronomic ranking stand. Whichever basis was used is
    reported in `district_gate`, and every option carries `district_grown` /
    `state_grown`, so the page can say why a crop is or is not offered.
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
    prev_family = _rotation_name(row['family'])
    prev_name = _rotation_name(row['crop'])
    prev_is_cereal = 'cereal' in prev_family

    # 2. Compute depleted soil
    N_after = max(0, N - row['N_loss'])
    P_after = max(0, P - row['P_loss'])
    K_after = max(0, K - row['K_loss'])

    depleted = np.array([N_after, P_after, K_after], dtype=float)

    # 3. Get candidate next crops
    candidates = [c.strip() for c in str(row['best_next_crops']).split(';')]
    district_crops, state_crops = _district_crop_sets(district, state)

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

        n_fix = cand_row['nitrogen_fixing'] == 'Yes'
        n_fix_bonus = 0.05 if (n_fix and N_after < 40) else 0.0
        # A legume after any cereal earns a break bonus even when N is not yet
        # depleted: that is the rotation every agronomy guide recommends.
        break_bonus = 0.08 if (n_fix and prev_is_cereal) else 0.0

        cand_family = _rotation_name(cand_row['family'])
        same_family = bool(cand_family) and cand_family == prev_family
        family_penalty = 0.15 if same_family else 0.0

        avoid_list = [
            _rotation_name(a) for a in
            str(cand_row.get('avoid_after') or '').replace(';', ',').split(',')
            if _rotation_name(a)
        ]
        avoids_prev = prev_name in avoid_list
        avoid_penalty = 0.30 if avoids_prev else 0.0

        hist = _district_crop_history(district, cand_row['crop'])
        history_score = min(
            1.0, 0.6 * float(hist['yield_score']) + 0.4 * min(
                1.0, float(hist['area_share']) / 0.15))

        final_score = (0.62 * cos_score + 0.18 * history_score
                       + n_fix_bonus + break_bonus
                       - family_penalty - avoid_penalty)
        final_score = float(np.clip(final_score, 0.0, 1.0))

        # Nutrient gap (how much fertiliser needed)
        n_gap = max(0, ideal[0] - N_after)
        p_gap = max(0, ideal[1] - P_after)
        k_gap = max(0, ideal[2] - K_after)

        cand_key = _HISTORY_ALIASES.get(_rotation_name(cand_row['crop']),
                                        _rotation_name(cand_row['crop']))
        results.append({
            'crop': cand_row['crop'],
            'family': cand_row['family'],
            'season': cand_row['season'],
            'district_grown': cand_key in district_crops,
            'state_grown': cand_key in state_crops,
            'cosine_score': float(round(cos_score, 4)),
            'n_fix_bonus': float(round(n_fix_bonus + break_bonus, 4)),
            'history_score': float(round(history_score, 4)),
            'same_family': same_family,
            'avoids_previous': avoids_prev,
            'penalty': float(round(family_penalty + avoid_penalty, 4)),
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

    # 5. Gate on district fit. The agronomic ranking stays intact in
    # `all_candidates`; `suggestions` only offers crops this district grows.
    gate = {'applied': False, 'district': district, 'basis': 'agronomic',
            'excluded': [], 'note': ''}
    if results and district:
        local = [r for r in results if r['district_grown']]
        state_only = [r for r in results if r['state_grown'] and not r['district_grown']]
        if local:
            eligible, basis = local, 'district'
            gate['note'] = ('Only crops this district grows are shown, ranked '
                            'by soil fit and its own yield record.')
        elif state_only:
            eligible, basis = state_only, 'state'
            gate['note'] = ('No district crop record covers these options, so '
                            'crops grown elsewhere in the state are shown.')
        else:
            eligible, basis = results, 'agronomic'
            gate['note'] = ('Neither the district nor the state has a record of '
                            'these crops - showing the agronomic ranking alone.')
        gate['applied'] = basis != 'agronomic'
        gate['basis'] = basis
        gate['excluded'] = [r['crop'] for r in results if r not in eligible]
        suggestions = eligible
    else:
        suggestions = results
        gate['note'] = ('Choose a district to filter out crops it does not '
                        'grow.')

    # 6. Warnings
    warnings_list = []
    if N_after < 20:
        warnings_list.append("Nitrogen critically low — prioritise nitrogen-fixing crop or add urea")
    if P_after < 10:
        warnings_list.append("Phosphorus very low — add DAP/SSP before next sowing")
    if K_after < 10:
        warnings_list.append("Potassium low — apply MOP before next season")
    if suggestions and suggestions[0].get('same_family'):
        warnings_list.append(
            f"Every listed option is in the {row['family']} family: sowing "
            "the same family repeatedly builds up soil-borne disease and "
            "pests. Consider a break crop if one suits your season.")
    if suggestions and all(s.get('avoids_previous') for s in suggestions):
        warnings_list.append(
            f"Every option for {row['crop']} is flagged as a poor follow-on "
            "crop. Widen to a different family if your season allows.")

    return {
        'season1_crop': row['crop'],
        'depleted_soil': {'N': float(N_after), 'P': float(P_after), 'K': float(K_after)},
        'suggestions': suggestions[:top_n],
        'district_gate': gate,
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
    state=None,
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
    result_s2 = get_rotation_suggestions(season1_crop, N, P, K, top_n=top_n,
                                         district=district, state=state)
    if 'error' in result_s2:
        return {"error": result_s2['error']}

    best_s2 = result_s2['suggestions'][0]
    s2_soil = result_s2['depleted_soil']

    # Season 3 preview
    result_s3 = get_rotation_suggestions(
        best_s2['crop'],
        s2_soil['N'], s2_soil['P'], s2_soil['K'],
        top_n=2, district=district, state=state
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
        # Which locality basis the season-2 list was held to, plus the crops it
        # dropped, so the page can explain the list instead of just showing it.
        'district_gate': result_s2.get('district_gate'),
        'warnings': result_s2['warnings'],
        'input_npk': {k: float(v) for k, v in {'N': N, 'P': P, 'K': K, 'ph': ph}.items()}
    }

# ------------------ FERTILIZER RECOMMENDATION ------------------

def fertilizer_extra_inputs(district=None, state=None, lat=None, lon=None,
                           temperature=None, humidity=None):
    """The three model inputs a soil test does not carry.

    The classifier is trained on temperature, organic carbon and moisture as
    well as NPK/pH, because those are what distinguish compost from urea in
    the dataset. Each is resolved from something the platform already holds,
    and `sources` says which, so the endpoint can report what it actually used
    rather than implying a laboratory measurement:

        temperature  live Open-Meteo reading for the district
        carbon       DES survey organic-carbon band shares -> weighted midpoint
        moisture     relative humidity expressed as a 0-1 fraction

    Anything unavailable falls back to the documented training defaults.
    """
    defaults = dict((_FERTILIZER_BUNDLE or {}).get("defaults") or {})
    out = {
        "temperature": float(defaults.get("temperature", 27.0)),
        "carbon": float(defaults.get("carbon", 0.62)),
        "moisture": round(float(defaults.get("moisture", 0.70)), 2),
    }
    sources = {"temperature": "default", "carbon": "default",
               "moisture": "default"}

    try:
        if temperature is not None:
            out["temperature"] = float(temperature)
            sources["temperature"] = "weather"
    except (TypeError, ValueError):
        pass

    try:
        if humidity is not None:
            pct = max(0.0, min(100.0, float(humidity)))
            out["moisture"] = round(pct / 100.0, 2)
            sources["moisture"] = "humidity"
    except (TypeError, ValueError):
        pass

    try:
        import district_data as dd
        oc = dd.organic_carbon(district, state, lat, lon)
        if oc and oc.get("value") is not None:
            out["carbon"] = float(oc["value"])
            out["carbon_band"] = oc.get("band")
            sources["carbon"] = oc.get("source", "district_soil_survey")
    except Exception as e:  # noqa: BLE001 - carbon is an input, not a dependency
        print(f"[fertilizer] carbon estimate unavailable: {e}")

    out["sources"] = sources
    return out


def recommend_fertilizer(crop, soil, n, p, k, ph, top_k=5, extras=None):
    """Ranked fertilisers for this crop, soil and soil test.

    Uses the trained classifier in `models/fertilizer_model.pkl` when present
    (see train_fertilizer_model.py). It reads everything the endpoint can
    supply - N, P, K, pH, soil class, crop, plus temperature, organic carbon
    and moisture - and beats the cosine retrieval it replaces by a wide margin
    (0.93 vs 0.56 accuracy on the shipped dataset). The old retrieval stays as
    the fallback so a checkout without the bundle keeps working.

    `extras` is the dict from `fertilizer_extra_inputs`; when it is omitted the
    model falls back to the training defaults, which keeps direct callers
    (tests, notebooks) working unchanged.

    Returns a DataFrame with Fertilizer / Similarity / Remark columns, which is
    the shape the endpoint and the page already use.
    """
    crop = crop.lower()
    soil = soil.lower()

    if _FERTILIZER_BUNDLE:
        rows = _fertilizer_model_rows(crop, soil, n, p, k, ph, top_k,
                                      extras=extras)
        if rows is not None:
            return rows

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


def _fertilizer_model_rows(crop, soil, n, p, k, ph, top_k, extras=None):
    """Classifier path: probability-ranked fertilisers, dataset remarks.

    `Similarity` is now the model's probability for that fertiliser rather
    than a cosine against the nearest row, so it is comparable across crops
    and it is what the ranking is actually based on. Rows keep the dataset's
    Remark text because that sentence is what the page shows.
    """
    bundle = _FERTILIZER_BUNDLE
    if crop not in bundle["crops"]:
        return None
    try:
        soils = bundle["soils"]
        crops = bundle["crops"]
        defaults = bundle.get("defaults") or {}
        extras = extras or {}
        # Built by column name from the bundle's own feature order, so the
        # served vector cannot drift from the trained one.
        values = {
            "Nitrogen": n,
            "Phosphorous": p,
            "Potassium": k,
            "PH": ph,
            "Temperature": extras.get("temperature",
                                      defaults.get("temperature", 27.0)),
            "Carbon": extras.get("carbon", defaults.get("carbon", 0.62)),
            "Moisture": extras.get("moisture", defaults.get("moisture", 0.70)),
        }
        numeric = bundle.get("numeric") or ["Nitrogen", "Phosphorous",
                                           "Potassium", "PH"]
        soil_vec = [1.0 if soil == s else 0.0 for s in soils]
        if not any(soil_vec):
            # Unseen spelling ("black"/"red"): let the dataset's own soil
            # classes stay neutral rather than silently picking the first.
            soil_vec = [0.0] * len(soils)
        crop_vec = [1.0 if crop == c else 0.0 for c in crops]
        row = np.array([[float(values[col]) for col in numeric]
                        + soil_vec + crop_vec])
        proba = bundle["model"].predict_proba(row)[0]
    except Exception as e:  # noqa: BLE001
        print(f"[fertilizer] model path failed: {e}")
        return None

    order = np.argsort(proba)[::-1][:max(top_k, 1)]
    out = []
    for i in order:
        name = bundle["classes"][i]
        out.append({
            "Fertilizer": name,
            "Similarity": round(float(proba[i]), 4),
            "Remark": bundle["remarks"].get(name, ""),
        })
    return pd.DataFrame(out)

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