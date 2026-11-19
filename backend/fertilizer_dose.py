"""
How much fertiliser to apply, in kg per hectare.

The ranked list answers *which* fertiliser; this module answers *how much*, and
it does not invent agronomy. Every number here is read from the ICAR documents
already shipped in `data/icar/`, or derived from them by the rule printed beside
it:

    Recommended dose of nutrients   FertiSolver user manual, Appendix-A (p22-23):
                                    N, P2O5, K2O and S in kg/ha per crop, plus the
                                    urea split percentages T1-T4.
    Fertiliser grades               Same manual, Table 3 (p17): DAP 18:46:0,
                                    urea 46:0:0, MOP 0:0:60, SOP 0:0:50,
                                    SSP 0:16:0, 12:32:16, 14:35:14.
    Soil test categories            Same manual, Table 1 (p13): N <282 / 282-560
                                    / >560, P <34 / 34-68 / >68, K <108 /
                                    108-280 / >280 kg/ha, pH <6.5 / 6.5-7.5 / >7.5.
    Adjustment for soil test        ICAR-IISS INM manual (p36): the general
                                    recommendation applies to the *medium*
                                    category, with "an arbitrary adjustment
                                    (decrease or increase by 25-50 per cent) for
                                    high and low categories". This module takes
                                    the conservative end - +25% when a nutrient
                                    is low, -25% when it is high - so a farmer is
                                    never pushed to the aggressive extreme the
                                    source leaves open.
    Lime                            The manual's worked example (p19) applies
                                    400 kg/ha of lime to a pH 5.5 plot, i.e. one
                                    pH unit below neutral. The rate below is
                                    scaled linearly from that example and is
                                    labelled as an estimate.

What is deliberately *not* here:

  * STCR prescription equations (IISS manual p37, e.g.
    FN = 6.38 T - 0.63 SN - 1.42 ON). They need district-specific calibration
    constants and a yield target, which this platform does not hold. Quoting the
    equation without them would be fabrication.
  * Crops with no row in Appendix-A: cotton, sugarcane, turmeric, ginger and
    barley. They get `available: False` and a straight explanation rather than a
    guessed dose.
  * The survey's smoothed N/P/K estimates are never classified against Table 1.
    They are band-share midpoints, not soil test values, so the district's own
    low/medium/high sample split decides its category instead.

Deterministic: no randomness, no network, no LLM. Same inputs, same kilograms.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# ICAR FertiSolver Appendix-A: recommended dose of nutrients (kg/ha)
# --------------------------------------------------------------------------

# (N, P2O5, K2O, S) plus the urea split schedule T1-T4 in percent.
# T1 = before transplanting / at last ploughing, T2 = at sowing or transplanting,
# T3 = 25-30 days after sowing, T4 = 40-50 days after sowing (manual p23).
ICAR_RDF: Dict[str, Dict[str, Any]] = {
    "arhar":            {"N": 25,  "P": 50, "K": 25, "S": 0,  "splits": (0, 100, 0, 0)},
    "black gram":       {"N": 25,  "P": 50, "K": 25, "S": 0,  "splits": (0, 100, 0, 0)},
    "chick pea":        {"N": 25,  "P": 50, "K": 25, "S": 0,  "splits": (0, 100, 0, 0)},
    "cow pea":          {"N": 20,  "P": 40, "K": 20, "S": 0,  "splits": (50, 0, 50, 0)},
    "field pea":        {"N": 25,  "P": 50, "K": 25, "S": 0,  "splits": (50, 0, 50, 0)},
    "green gram":       {"N": 20,  "P": 50, "K": 25, "S": 0,  "splits": (0, 100, 0, 0)},
    "lentil":           {"N": 25,  "P": 50, "K": 25, "S": 0,  "splits": (0, 100, 0, 0)},
    "linseed irrigated": {"N": 50, "P": 30, "K": 20, "S": 20, "splits": (0, 50, 50, 0)},
    "linseed unirrigated": {"N": 30, "P": 20, "K": 20, "S": 20, "splits": (0, 50, 50, 0)},
    "maize":            {"N": 120, "P": 60, "K": 40, "S": 0,  "splits": (0, 50, 50, 0)},
    "millet":           {"N": 40,  "P": 30, "K": 20, "S": 0,  "splits": (0, 50, 50, 0)},
    "mustard":          {"N": 50,  "P": 25, "K": 25, "S": 20, "splits": (0, 50, 50, 0)},
    "rice bean":        {"N": 20,  "P": 40, "K": 20, "S": 0,  "splits": (0, 100, 0, 0)},
    "rice-lowland":     {"N": 120, "P": 60, "K": 40, "S": 0,  "splits": (50, 25, 25, 0)},
    "rice-midland":     {"N": 80,  "P": 40, "K": 20, "S": 0,  "splits": (50, 25, 25, 0)},
    "rice-upland":      {"N": 40,  "P": 20, "K": 20, "S": 0,  "splits": (50, 25, 25, 0)},
    "wheat-irrigated":  {"N": 120, "P": 60, "K": 40, "S": 0,  "splits": (50, 25, 25, 0)},
    "wheat-unirrigated": {"N": 60, "P": 30, "K": 20, "S": 0,  "splits": (50, 50, 0, 0)},
    "soybean":          {"N": 25,  "P": 50, "K": 20, "S": 40, "splits": (0, 100, 0, 0)},
    "groundnuts":       {"N": 25,  "P": 50, "K": 20, "S": 40, "splits": (0, 100, 0, 0)},
    "til":              {"N": 40,  "P": 20, "K": 20, "S": 0,  "splits": (0, 50, 50, 0)},
    "niger (surguja)":  {"N": 20,  "P": 20, "K": 20, "S": 0,  "splits": (0, 100, 0, 0)},
    "sunflower":        {"N": 40,  "P": 50, "K": 25, "S": 25, "splits": (0, 100, 0, 0)},
    # Vegetables (manual p22-23)
    "cabbage":          {"N": 200, "P": 35, "K": 50, "S": 0,  "splits": (50, 25, 25, 0)},
    "cauliflower":      {"N": 150, "P": 26, "K": 50, "S": 0,  "splits": (50, 25, 25, 0)},
    "brinjal":          {"N": 120, "P": 26, "K": 50, "S": 0,  "splits": (34, 0, 33, 33)},
    "chilli":           {"N": 60,  "P": 22, "K": 42, "S": 0,  "splits": (34, 0, 33, 33)},
    "capsicum":         {"N": 60,  "P": 44, "K": 42, "S": 0,  "splits": (34, 0, 33, 33)},
    "tomato":           {"N": 120, "P": 26, "K": 50, "S": 0,  "splits": (34, 0, 33, 33)},
    "okra":             {"N": 120, "P": 35, "K": 50, "S": 0,  "splits": (0, 50, 50, 0)},
    "french bean":      {"N": 60,  "P": 22, "K": 42, "S": 0,  "splits": (50, 0, 50, 0)},
    "carrot":           {"N": 60,  "P": 22, "K": 62, "S": 0,  "splits": (0, 50, 0, 50)},
    "radish":           {"N": 80,  "P": 26, "K": 50, "S": 0,  "splits": (0, 50, 50, 0)},
    "cucumber":         {"N": 50,  "P": 17, "K": 33, "S": 0,  "splits": (0, 50, 50, 0)},
    "ridge gourd":      {"N": 50,  "P": 26, "K": 42, "S": 0,  "splits": (50, 0, 50, 0)},
    "pointed gourd":    {"N": 120, "P": 26, "K": 42, "S": 0,  "splits": (34, 0, 33, 33)},
    "bottle gourd":     {"N": 50,  "P": 26, "K": 42, "S": 0,  "splits": (0, 50, 50, 0)},
    "bitter gourd":     {"N": 50,  "P": 26, "K": 42, "S": 0,  "splits": (0, 50, 50, 0)},
    "potato":           {"N": 125, "P": 39, "K": 75, "S": 0,  "splits": (50, 50, 0, 0)},
    "onion":            {"N": 80,  "P": 26, "K": 66, "S": 0,  "splits": (0, 50, 50, 0)},
}

# Crop names as the app spells them -> the manual's row.
CROP_ROWS: Dict[str, str] = {
    "rice": "rice-midland",
    "paddy": "rice-midland",
    "wheat": "wheat-irrigated",
    "maize": "maize",
    "soybean": "soybean",
    "soyabean": "soybean",
    "chickpea": "chick pea",
    "chick pea": "chick pea",
    "gram": "chick pea",
    "pigeon pea": "arhar",
    "pigeonpea": "arhar",
    "arhar": "arhar",
    "tur": "arhar",
    "red gram": "arhar",
    "green gram": "green gram",
    "moong": "green gram",
    "mung": "green gram",
    "black gram": "black gram",
    "urad": "black gram",
    "lentil": "lentil",
    "masoor": "lentil",
    "cowpea": "cow pea",
    "field pea": "field pea",
    "groundnut": "groundnuts",
    "groundnuts": "groundnuts",
    "peanut": "groundnuts",
    "mustard": "mustard",
    "sunflower": "sunflower",
    "sesame": "til",
    "til": "til",
    "linseed": "linseed irrigated",
    "jowar": "millet",
    "sorghum": "millet",
    "bajra": "millet",
    "pearl millet": "millet",
    "ragi": "millet",
    "finger millet": "millet",
    "millet": "millet",
    "potato": "potato",
    "tomato": "tomato",
    "onion": "onion",
    "chilli": "chilli",
    "chili": "chilli",
    "capsicum": "capsicum",
    "brinjal": "brinjal",
    "okra": "okra",
    "bhindi": "okra",
    "cabbage": "cabbage",
    "cauliflower": "cauliflower",
    "carrot": "carrot",
    "radish": "radish",
    "cucumber": "cucumber",
    "ridge gourd": "ridge gourd",
    "pointed gourd": "pointed gourd",
    "bottle gourd": "bottle gourd",
    "bitter gourd": "bitter gourd",
    "french bean": "french bean",
}

# Crops the app offers that the manual's Appendix-A has no row for. Named here
# so the response can say why instead of returning a made-up number.
NO_ROW = {
    "cotton": "Cotton is not in the manual's Appendix-A crop list",
    "sugarcane": "Sugarcane is not in the manual's Appendix-A crop list",
    "turmeric": "Turmeric is not in the manual's Appendix-A crop list",
    "ginger": "Ginger is not in the manual's Appendix-A crop list",
    "barley": "Barley is not in the manual's Appendix-A crop list",
}

# --------------------------------------------------------------------------
# ICAR Table 3 grades: % N, % P2O5, % K2O, % S
# --------------------------------------------------------------------------

GRADES: Dict[str, Tuple[float, float, float, float]] = {
    "Urea": (46.0, 0.0, 0.0, 0.0),
    "DAP": (18.0, 46.0, 0.0, 0.0),
    "Muriate of Potash": (0.0, 0.0, 60.0, 0.0),
    "Single Super Phosphate": (0.0, 16.0, 0.0, 11.0),
    "Sulphate of Potash": (0.0, 0.0, 50.0, 18.0),
    "12:32:16": (12.0, 32.0, 16.0, 0.0),
    "14:35:14": (14.0, 35.0, 14.0, 0.0),
}

# --------------------------------------------------------------------------
# ICAR Table 1: soil test categories (kg/ha for N, P2O5 and K2O; pH for reaction)
# --------------------------------------------------------------------------

THRESHOLDS = {
    "N": (282.0, 560.0),   # low < 282, medium 282-560, high > 560
    "P": (34.0, 68.0),
    "K": (108.0, 280.0),
}

# IISS INM manual p36: medium category gets the recommendation as printed; low
# and high are adjusted by 25-50%. Conservative end of that range.
ADJUSTMENT = {"low": 1.25, "medium": 1.0, "high": 0.75}

CITATIONS = [
    {"doc": "ICAR fertiliser dose calculator — user manual", "page": 22,
     "claim": "recommended dose of N, P2O5, K2O and S per crop (Appendix-A)"},
    {"doc": "ICAR fertiliser dose calculator — user manual", "page": 23,
     "claim": "urea split stages T1-T4 (Appendices-A notes)"},
    {"doc": "ICAR fertiliser dose calculator — user manual", "page": 17,
     "claim": "fertiliser grades: DAP 18:46:0, urea 46:0:0, MOP 0:0:60, SSP 0:16:0"},
    {"doc": "ICAR fertiliser dose calculator — user manual", "page": 13,
     "claim": "soil test category thresholds (Table 1)"},
    {"doc": "ICAR-IISS Integrated Nutrient Management training manual", "page": 36,
     "claim": "medium category takes the printed dose, low/high adjusted 25-50%"},
    {"doc": "ICAR fertiliser dose calculator — user manual", "page": 19,
     "claim": "worked example: lime 400 kg/ha at pH 5.5"},
]

STAGES = [
    "T1 · before transplanting / last ploughing",
    "T2 · at sowing or transplanting",
    "T3 · 25-30 days after sowing",
    "T4 · 40-50 days after sowing",
]


def classify(value: Optional[float], nutrient: str) -> Optional[str]:
    """Low / medium / high for a real soil test value, using ICAR Table 1."""
    if value is None:
        return None
    low_max, medium_max = THRESHOLDS[nutrient]
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < low_max:
        return "low"
    if v <= medium_max:
        return "medium"
    return "high"


def classify_ph(ph: Optional[float]) -> Optional[str]:
    """Acidic / normal / basic, using ICAR Table 1 (6.5 and 7.5)."""
    if ph is None:
        return None
    try:
        v = float(ph)
    except (TypeError, ValueError):
        return None
    if v < 6.5:
        return "acidic"
    if v <= 7.5:
        return "normal"
    return "basic"


def lime_kg(ph: Optional[float]) -> Optional[int]:
    """Lime requirement estimate, scaled from the manual's 400 kg/ha at pH 5.5.

    One pH unit below 6.5 therefore asks for 400 kg/ha, and half a unit for 200.
    Labelled an estimate everywhere it surfaces: it is a linear scaling of a
    single worked example, not a lime-requirement curve.
    """
    if ph is None:
        return None
    try:
        v = float(ph)
    except (TypeError, ValueError):
        return None
    if v >= 6.5:
        return None
    return int(round((6.5 - v) * 400 / 10.0) * 10)


def crop_row(crop: str) -> Optional[str]:
    key = (crop or "").strip().lower()
    if key in CROP_ROWS:
        return CROP_ROWS[key]
    # tolerate plurals and spacing ("pigeon peas", "green grams")
    singular = key[:-1] if key.endswith("s") and key[:-1] in CROP_ROWS else None
    if singular:
        return CROP_ROWS[singular]
    return CROP_ROWS.get(" ".join(key.split()))


def _round5(x: float) -> float:
    """Round a nutrient requirement to the nearest 5 kg/ha."""
    return float(int(round(x / 5.0) * 5))


def _one(x: float) -> float:
    return round(float(x), 1)


def compute_dose(
    crop: str,
    n: Optional[float],
    p: Optional[float],
    k: Optional[float],
    ph: Optional[float],
    *,
    levels: Optional[Dict[str, str]] = None,
    levels_source: Optional[str] = None,
    urea_preference: Optional[str] = None,
) -> Dict[str, Any]:
    """kg/ha of each product for this crop and this soil.

    `levels` is the soil's low/medium/high status per nutrient when it is known
    from the district survey; otherwise it is derived from the soil test values
    with ICAR Table 1. Missing everything lands on the medium category, which is
    where the manual's printed dose applies, and says so.

    Returns a dict with `available`, the requirement, the product quantities and
    the schedule. It never raises: an unknown crop returns available=False with
    the reason.
    """
    row_key = crop_row(crop)
    levels = dict(levels or {})
    notes: List[str] = []

    if row_key is None:
        reason = NO_ROW.get((crop or "").strip().lower())
        if reason is None:
            reason = (f"{crop} has no row in the manual's Appendix-A dose table")
        return {
            "available": False,
            "crop": crop,
            "reason": reason,
            "note": ("No ICAR dose row for this crop in the shipped corpus, so no "
                     "kg/ha figure is given rather than a guessed one. The soil "
                     "status reading below is still computed from Table 1."),
            "soil_status": _status_payload(n, p, k, ph, levels, levels_source),
            "citations": CITATIONS,
        }

    row = ICAR_RDF[row_key]

    # --- status per nutrient -------------------------------------------
    status: Dict[str, str] = {}
    basis: Dict[str, str] = {}
    for nut, value in (("N", n), ("P", p), ("K", k)):
        if levels.get(nut) in ADJUSTMENT:
            status[nut] = levels[nut]
            basis[nut] = levels_source or "district_soil_survey"
        else:
            derived = classify(value, nut)
            if derived:
                status[nut] = derived
                basis[nut] = "soil_test_ICAR_Table1"
            else:
                status[nut] = "medium"
                basis[nut] = "default_medium"

    # --- requirement ----------------------------------------------------
    requirement: Dict[str, float] = {}
    base: Dict[str, float] = {}
    for nut, col in (("N", "N"), ("P2O5", "P"), ("K2O", "K"), ("S", "S")):
        printed = float(row[col])
        base[nut] = printed
        if printed <= 0:
            requirement[nut] = 0.0
            continue
        factor = ADJUSTMENT.get(status.get(nut.split("2")[0], "medium"), 1.0)
        requirement[nut] = _round5(printed * factor)

    # --- products -------------------------------------------------------
    products: List[Dict[str, Any]] = []
    # pH is judged from the pH value itself, because the lime quantity is
    # derived from that value - a survey band that disagreed with the number
    # would produce a dose that contradicts the card above it.
    ph_status = classify_ph(ph)
    if ph_status == "acidic":
        amount = lime_kg(ph)
        entry: Dict[str, Any] = {
            "name": "Lime",
            "kg_per_ha": amount,
            "supplies": {},
            "role": "soil reaction amendment (apply before the crop fertiliser)",
        }
        if amount is None:
            entry["kg_per_ha"] = 400
            notes.append(
                "pH category is acidic from the district survey but no pH value "
                "was given, so the manual's example rate (400 kg/ha) is shown.")
        products.append(entry)

    p_req = requirement["P2O5"]
    s_req = requirement["S"]
    n_req = requirement["N"]
    k_req = requirement["K2O"]

    # S first: SSP carries 16% P2O5 with 11% S, so it pays for both.
    ssp_kg = (s_req / (GRADES["Single Super Phosphate"][3] / 100.0)) if s_req > 0 else 0.0
    ssp_p = ssp_kg * GRADES["Single Super Phosphate"][1] / 100.0
    ssp_p = min(ssp_p, p_req)
    if ssp_kg > 0:
        products.append({
            "name": "Single Super Phosphate",
            "kg_per_ha": _one(ssp_kg),
            "supplies": {"P2O5": _one(ssp_p), "S": _one(ssp_kg * 0.11)},
            "role": "phosphorus with sulphur",
        })

    p_left = max(0.0, p_req - ssp_p)
    dap_kg = p_left / (GRADES["DAP"][1] / 100.0) if p_left > 0 else 0.0
    dap_n = dap_kg * GRADES["DAP"][0] / 100.0
    if dap_kg > 0:
        products.append({
            "name": "DAP",
            "kg_per_ha": _one(dap_kg),
            "supplies": {"N": _one(dap_n), "P2O5": _one(p_left)},
            "role": "basal phosphorus (with starter nitrogen)",
        })

    k_kg = k_req / (GRADES["Muriate of Potash"][2] / 100.0) if k_req > 0 else 0.0
    if k_kg > 0:
        products.append({
            "name": "Muriate of Potash",
            "kg_per_ha": _one(k_kg),
            "supplies": {"K2O": _one(k_req)},
            "role": "basal potash",
        })

    n_left = max(0.0, n_req - dap_n)
    urea_kg = n_left / (GRADES[urea_preference or "Urea"][0] / 100.0) \
        if n_left > 0 else 0.0
    if urea_kg > 0:
        products.append({
            "name": urea_preference or "Urea",
            "kg_per_ha": _one(urea_kg),
            "supplies": {"N": _one(n_left)},
            "role": "nitrogen top-dressing (split as below)",
        })

    splits = row["splits"]
    schedule = [
        {"stage": STAGES[i], "percent": int(splits[i]),
         "kg_per_ha": _one(urea_kg * splits[i] / 100.0)}
        for i in range(4) if splits[i]
    ]

    total_n = sum(p["supplies"].get("N", 0) for p in products)
    total_p = sum(p["supplies"].get("P2O5", 0) for p in products)
    total_k = sum(p["supplies"].get("K2O", 0) for p in products)

    notes.append(
        f"Dose is the ICAR manual's printed recommendation for “{row_key}”"
        f" ({row['N']}:{row['P']}:{row['K']} kg/ha N:P2O5:K2O), adjusted by "
        f"+25% where a nutrient is low and -25% where it is high, and left at "
        f"the printed dose where it is medium (IISS manual p36).")
    if row_key.startswith("rice"):
        notes.append(
            "Rice uses the manual's midland row; its lowland (120:60:40) and "
            "upland (40:20:20) rows differ by land type.")
    if row_key.startswith("wheat"):
        notes.append(
            "Wheat uses the irrigated row; the manual's unirrigated row is 60:30:20.")
    if (crop or "").strip().lower() in {"jowar", "bajra", "ragi", "sorghum",
                                        "pearl millet", "finger millet"}:
        notes.append(
            "The manual publishes a single “Millet” row (40:30:20) for these "
            "millets; state package-of-practices doses differ slightly.")
    if ph_status == "basic":
        notes.append(
            "Soil is basic. The manual gives no gypsum rate, so no amendment "
            "quantity is shown; use your local recommendation for sodic soils.")
    if s_req > 0:
        notes.append(
            f"This crop's ICAR row requires {s_req:.0f} kg/ha of sulphur, "
            "supplied here through single super phosphate.")

    return {
        "available": True,
        "crop": crop,
        "table_row": row_key,
        "unit": "kg/ha",
        "requirement": {key: _one(val) for key, val in requirement.items()},
        "printed_dose": {key: float(val) for key, val in base.items()},
        "soil_status": _status_payload(n, p, k, ph, levels, levels_source,
                                       status=status, basis=basis),
        "products": products,
        "supplies_total": {"N": _one(total_n), "P2O5": _one(total_p),
                           "K2O": _one(total_k)},
        "urea_schedule": schedule,
        "citations": CITATIONS,
        "notes": notes,
    }


# ICAR FertiSolver Appendix-B (p24) gives the tool's fertiliser prices in
# Rs/kg: DAP 22.00, 12:32:16 23.00, 14:35:14 23.30, SSP 8.56, urea 5.68,
# MOP 11.00, SOP 58.00. Lime comes from the manual's worked example (p19):
# 400 kg cost Rs 2000, i.e. Rs 5/kg. These are 2021 prices, so anything derived
# from them is reported with the year attached.
GRADE_PRICES_INR_PER_KG: Dict[str, float] = {
    "DAP": 22.00,
    "12:32:16": 23.00,
    "14:35:14": 23.30,
    "Single Super Phosphate": 8.56,
    "Urea": 5.68,
    "Muriate of Potash": 11.00,
    "Sulphate of Potash": 58.00,
    "Lime": 5.00,
}
PRICE_YEAR = 2021


def estimate_cost(dose: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What the dose costs per hectare at the manual's own prices.

    Returns None when the dose has no products. `excludes` travels with the
    number because this is a fertiliser bill, not a cost of cultivation: seed,
    labour, machinery, irrigation and transport are not in it, so a caller must
    not print it as profit.
    """
    products = dose.get("products") or []
    if not products:
        return None
    total = 0.0
    priced: List[Dict[str, Any]] = []
    for product in products:
        price = GRADE_PRICES_INR_PER_KG.get(product.get("name"))
        kg = product.get("kg_per_ha")
        if price is None or kg is None:
            continue
        cost = round(float(kg) * price, 2)
        total += cost
        priced.append({"name": product["name"], "kg_per_ha": kg,
                       "inr_per_kg": price, "cost_inr": cost})
    if not priced:
        return None
    return {
        "fertiliser_cost_per_ha": round(total, 2),
        "priced_at": f"ICAR FertiSolver Appendix-B, {PRICE_YEAR} prices",
        "lines": priced,
        "excludes": ["seed", "labour", "machinery", "irrigation", "transport"],
        "note": ("Fertiliser cost only, at the manual's 2021 prices; it is not a "
                 "cost of cultivation and must not be read as profit."),
    }


def _status_payload(n, p, k, ph, levels, levels_source, status=None,
                    basis=None) -> Dict[str, Any]:
    keyed = {"N": status.get("N") if status else None,
             "P": status.get("P") if status else None,
             "K": status.get("K") if status else None}
    values = {"N": n, "P": p, "K": k}
    if status is None:
        for nut in ("N", "P", "K"):
            keyed[nut] = levels.get(nut) or classify(values[nut], nut)
    ph_status = classify_ph(ph)
    if ph_status is None and levels.get("pH") in {"acidic", "normal", "basic"}:
        ph_status = levels["pH"]
    return {
        "levels": keyed,
        "ph": ph_status,
        "values": {nut: (None if values[nut] is None else _one(values[nut]))
                   for nut in ("N", "P", "K")},
        "basis": basis or {"N": levels_source or "district_soil_survey",
                           "P": levels_source or "district_soil_survey",
                           "K": levels_source or "district_soil_survey"},
    }
