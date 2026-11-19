"""
Tests for the kg/ha dose layer.

The point of these is that the numbers a farmer reads are traceable to the ICAR
tables rather than to a guess, and that they are stable: the same soil and crop
must produce the same kilograms on every request.
"""
from __future__ import annotations

import pytest

import fertilizer_dose as fd


def test_status_thresholds_are_the_icar_table1_values():
    """Table 1 p13: N 282/560, P 34/68, K 108/280, pH 6.5/7.5."""
    assert fd.classify(100, "N") == "low"
    assert fd.classify(300, "N") == "medium"
    assert fd.classify(600, "N") == "high"
    assert fd.classify(30, "P") == "low"
    assert fd.classify(50, "P") == "medium"
    assert fd.classify(70, "P") == "high"
    assert fd.classify(100, "K") == "low"
    assert fd.classify(200, "K") == "medium"
    assert fd.classify(300, "K") == "high"
    assert fd.classify_ph(5.9) == "acidic"
    assert fd.classify_ph(6.9) == "normal"
    assert fd.classify_ph(8.0) == "basic"


def test_printed_doses_come_from_the_manual_row():
    """Appendix-A p22: rice-midland 80:40:20, wheat-irrigated 120:60:40."""
    rice = fd.compute_dose("Rice", 300, 50, 200, 6.8)
    assert rice["table_row"] == "rice-midland"
    assert rice["printed_dose"] == {"N": 80.0, "P2O5": 40.0, "K2O": 20.0, "S": 0.0}

    wheat = fd.compute_dose("Wheat", 300, 50, 200, 6.8)
    assert wheat["printed_dose"]["N"] == 120.0


def test_medium_soil_gets_the_printed_dose_untouched():
    """IISS p36: the printed dose applies to the medium category."""
    dose = fd.compute_dose("Maize", 300, 50, 200, 6.8)
    assert dose["soil_status"]["levels"] == {"N": "medium", "P": "medium",
                                             "K": "medium"}
    assert dose["requirement"] == {"N": 120.0, "P2O5": 60.0, "K2O": 40.0, "S": 0.0}


def test_low_and_high_are_adjusted_by_the_documented_25_percent():
    low = fd.compute_dose("Maize", 100, 20, 50, 6.8)
    assert low["requirement"]["N"] == pytest.approx(150.0)   # 120 * 1.25
    assert low["requirement"]["P2O5"] == pytest.approx(75.0)  # 60 * 1.25
    assert low["requirement"]["K2O"] == pytest.approx(50.0)   # 40 * 1.25

    high = fd.compute_dose("Maize", 600, 80, 300, 6.8)
    assert high["requirement"]["N"] == pytest.approx(90.0)   # 120 * 0.75
    assert high["requirement"]["K2O"] == pytest.approx(30.0)


def test_district_band_levels_override_the_value_classification():
    """A survey band is a band; it must not be re-thresholded as kg/ha."""
    dose = fd.compute_dose("Maize", 300, 50, 200, 6.8,
                           levels={"N": "high", "P": "low"},
                           levels_source="district_soil_survey")
    assert dose["soil_status"]["levels"]["N"] == "high"
    assert dose["requirement"]["N"] == pytest.approx(90.0)
    assert dose["soil_status"]["basis"]["N"] == "district_soil_survey"


def test_products_supply_the_requirement():
    """DAP 18:46:0, MOP 0:0:60 and urea 46:0:0 must add up to the requirement."""
    dose = fd.compute_dose("Potato", 300, 50, 200, 6.9)
    req = dose["requirement"]
    totals = dose["supplies_total"]
    assert totals["N"] == pytest.approx(req["N"], abs=1.0)
    assert totals["P2O5"] == pytest.approx(req["P2O5"], abs=1.0)
    assert totals["K2O"] == pytest.approx(req["K2O"], abs=1.0)

    grades = {p["name"]: p for p in dose["products"]}
    dap = grades["DAP"]["kg_per_ha"]
    assert dap == pytest.approx(req["P2O5"] / 0.46, abs=0.5)
    mop = grades["Muriate of Potash"]["kg_per_ha"]
    assert mop == pytest.approx(req["K2O"] / 0.60, abs=0.5)


def test_sulphur_crops_are_supplied_through_ssp():
    """Soybean's ICAR row needs 40 kg/ha S; SSP 0:16:0 carries 11% S."""
    dose = fd.compute_dose("Soybean", 300, 50, 200, 6.8)
    ssp = next(p for p in dose["products"] if p["name"] == "Single Super Phosphate")
    assert ssp["kg_per_ha"] == pytest.approx(40 / 0.11, abs=0.5)
    assert ssp["supplies"]["S"] == pytest.approx(40.0, abs=0.5)


def test_urea_schedule_matches_the_manual_split():
    """Maize splits 0/50/50/0 (p23): the first stage can carry no urea."""
    dose = fd.compute_dose("Maize", 300, 50, 200, 6.8)
    stages = [s["stage"][:2] for s in dose["urea_schedule"]]
    assert stages == ["T2", "T3"]
    total = sum(s["kg_per_ha"] for s in dose["urea_schedule"])
    urea = next(p for p in dose["products"] if p["name"] == "Urea")
    assert total == pytest.approx(urea["kg_per_ha"], abs=0.2)


def test_acid_soil_leads_with_lime():
    dose = fd.compute_dose("Wheat", 300, 50, 200, 5.5)
    lime = dose["products"][0]
    assert lime["name"] == "Lime"
    assert lime["kg_per_ha"] == 400            # the manual's worked example
    assert fd.compute_dose("Wheat", 300, 50, 200, 5.2)["products"][0]["kg_per_ha"] == 520
    assert fd.compute_dose("Wheat", 300, 50, 200, 6.9)["products"][0]["name"] != "Lime"


def test_crops_absent_from_the_manual_get_no_invented_dose():
    for crop in ("Cotton", "Sugarcane", "Turmeric", "Ginger", "Barley",
                 "Dragonfruit"):
        dose = fd.compute_dose(crop, 300, 50, 200, 6.8)
        assert dose["available"] is False
        assert dose["reason"]
        assert "products" not in dose


def test_dose_is_deterministic():
    runs = [fd.compute_dose("Rice", 120, 30, 150, 6.4) for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_every_app_crop_resolves_to_a_row_or_a_reason():
    """No app crop may fall through to a bare None without an explanation."""
    app_crops = ["Rice", "Wheat", "Maize", "Cotton", "Soybean", "Sugarcane",
                 "Chickpea", "Pigeon Pea", "Green Gram", "Black Gram", "Lentil",
                 "Groundnut", "Mustard", "Sunflower", "Potato", "Tomato",
                 "Onion", "Chilli", "Turmeric", "Ginger", "Jowar", "Bajra",
                 "Ragi", "Barley"]
    for crop in app_crops:
        dose = fd.compute_dose(crop, 300, 50, 200, 6.8)
        assert dose["available"] or dose["reason"], crop
        if dose["available"]:
            assert dose["products"], crop


# ─────────────────────── endpoint wiring ──────────────────────────────────

def test_endpoint_returns_a_dose_with_citations(client):
    r = client.post("/fertilizer/recommend", json={
        "crop": "Rice", "soil": "Loamy", "N": 300, "P": 50, "K": 200,
        "PH": 6.6, "district": "Kolar", "state": "Karnataka"})
    assert r.status_code == 200
    dose = r.json()["dose"]
    assert dose["available"] is True
    assert dose["products"]
    assert dose["citations"][0]["page"] == 22
    assert dose["unit"] == "kg/ha"


def test_endpoint_explains_a_missing_dose(client):
    r = client.post("/fertilizer/recommend", json={
        "crop": "Cotton", "soil": "Black", "N": 300, "P": 50, "K": 200,
        "PH": 7.6, "district": "Nagpur", "state": "Maharashtra"})
    assert r.status_code == 200
    dose = r.json()["dose"]
    assert dose["available"] is False
    assert "Appendix-A" in dose["reason"]


def test_neutral_defaults_are_not_classified_as_low(client):
    """With no soil test and no survey, the printed dose applies unadjusted.

    The 90/40/40 fallback is a neutral default, not a measurement; classifying
    it against Table 1 would report a low-N soil and push 25% extra urea on a
    farm whose soil was never tested.
    """
    r = client.post("/fertilizer/recommend", json={
        "crop": "Rice", "soil": "Loamy", "district": "Nowhere Nagar",
        "state": "Atlantis"})
    assert r.status_code == 200
    dose = r.json()["dose"]
    assert dose["soil_status"]["levels"] == {"N": "medium", "P": "medium",
                                             "K": "medium"}
    assert dose["requirement"]["N"] == 80.0      # rice-midland printed 80
    assert dose["soil_status"]["basis"]["N"] == "default_medium"


def test_endpoint_dose_is_stable_across_calls(client):
    body = {"crop": "Maize", "soil": "Loamy", "N": 120, "P": 30, "K": 150,
            "PH": 6.4, "district": "Kolar", "state": "Karnataka"}
    first = client.post("/fertilizer/recommend", json=body).json()["dose"]
    second = client.post("/fertilizer/recommend", json=body).json()["dose"]
    assert first == second
