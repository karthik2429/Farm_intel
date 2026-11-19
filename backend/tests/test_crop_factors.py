"""
Does the crop recommendation actually use every factor it claims?

The advisor's subtitle says "ranked on your soil, climate, season, district
cropping and mandi returns". These tests hold it to that: every crop in the
answer must carry each factor, the weights must be the ones in the code, and the
money terms must reconcile (margin = gross return - fertiliser bill).
"""
from __future__ import annotations

import pytest

import fertilizer_dose


def _answer(client, **overrides):
    body = {"district": "Kolar", "state": "Karnataka", "season": "kharif"}
    body.update(overrides)
    r = client.post("/predict", json=body)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_every_alternative_carries_all_factors(client):
    body = _answer(client)
    assert body["alternatives"], body
    required = ("ml_prob", "ml_source", "soil_fit", "climate_fit",
                "season_fit", "hist_score", "region_share", "locality",
                "market_score", "market_price", "gross_return_per_ha")
    for alt in body["alternatives"]:
        missing = [k for k in required if k not in alt]
        assert not missing, f"{alt['crop']} is missing {missing}"


def test_factors_are_in_range(client):
    for alt in _answer(client)["alternatives"]:
        for key in ("soil_fit", "climate_fit", "season_fit", "market_score",
                    "locality", "hist_score"):
            if alt.get(key) is not None:
                assert 0.0 <= float(alt[key]) <= 1.0, (alt["crop"], key)
        if alt.get("region_share") is not None:
            assert 0.0 <= float(alt["region_share"]) <= 1.0


def test_market_factor_is_derived_from_price_and_yield(client):
    """market_score must scale with the real gross return, not be decorative."""
    alts = _answer(client)["alternatives"]
    grosses = [a["gross_return_per_ha"] for a in alts
               if a.get("gross_return_per_ha")]
    assert grosses, "no crop had a priceable gross return"
    top = max(grosses)
    for alt in alts:
        gross = alt.get("gross_return_per_ha")
        if not gross:
            continue
        expected = float(gross) / top
        assert alt["market_score"] == pytest.approx(expected, abs=0.02), alt["crop"]


def test_margin_equals_gross_minus_fertiliser_cost(client):
    checked = 0
    for alt in _answer(client)["alternatives"]:
        gross = alt.get("gross_return_per_ha")
        cost = alt.get("fertiliser_cost_per_ha")
        margin = alt.get("margin_after_fertiliser_per_ha")
        if gross is None or cost is None:
            assert margin is None, alt["crop"]
            continue
        assert margin == pytest.approx(gross - cost, abs=0.02), alt["crop"]
        assert alt.get("cost_basis")
        checked += 1
    assert checked, "no crop carried a fertiliser cost to reconcile"


def test_fertiliser_cost_matches_the_manual_prices():
    """ICAR Appendix-B 2021: DAP 22, urea 5.68, MOP 11 per kg."""
    dose = fertilizer_dose.compute_dose(
        "Maize", None, None, None, None,
        levels={"N": "medium", "P": "medium", "K": "medium"},
        levels_source="district_soil_survey")
    estimate = fertilizer_dose.estimate_cost(dose)
    assert estimate["fertiliser_cost_per_ha"] > 0
    assert "2021" in estimate["priced_at"]

    products = {p["name"]: p["kg_per_ha"] for p in dose["products"]}
    expected = (products["DAP"] * 22.00
                + products["Muriate of Potash"] * 11.00
                + products["Urea"] * 5.68)
    assert estimate["fertiliser_cost_per_ha"] == pytest.approx(expected, abs=0.05)
    # A fertiliser bill must never be presented as a cost of cultivation.
    assert "labour" in estimate["excludes"]
    assert "not a cost of cultivation" in estimate["note"]


def test_display_labels_resolve_to_agronomy():
    """"Ragi (Finger Millet)" is a model label and must still find its row.

    The results page labelled the top crop that way, so the yield, duration and
    price for the crop it recommended were blank while the same crop lower down
    had them.
    """
    import crop_info

    labels = {
        "Ragi (Finger Millet)": "ragi",
        "Tur (Pigeon Pea)": "pigeon pea",
        "Jowar (Sorghum)": "jowar",
        "Moong (Green Gram)": "green gram",
        "Urad (Black Gram)": "black gram",
        "Gram (Chickpea)": "chickpea",
        "Lentil (Masoor)": "lentil",
        "Bajra (Pearl Millet)": "bajra",
    }
    info = crop_info.get_crop_info(list(labels))
    for label, expected in labels.items():
        row = info[label]
        assert row["canonical"] == expected, (label, row["canonical"])
        assert row.get("yield_t_ha"), f"{label} has no yield band"
        assert row.get("duration_days"), f"{label} has no duration"


def test_user_supplied_soil_changes_the_answer(client):
    """Soil is an input, not decoration: a very different soil test must matter."""
    base = _answer(client)
    poor = _answer(client, N=20, P=10, K=10, ph=4.8)
    rich = _answer(client, N=280, P=90, K=300, ph=7.4)
    assert poor["soil_used"] != rich["soil_used"]
    scores = [
        {a["crop"]: a["soil_fit"] for a in answer["alternatives"]}
        for answer in (poor, rich)
    ]
    shared = set(scores[0]) & set(scores[1])
    assert shared
    assert any(scores[0][c] != scores[1][c] for c in shared), \
        "soil_fit did not respond to the soil test"


def test_rainfall_changes_the_climate_term(client):
    dry = _answer(client, rainfall=1.0)
    wet = _answer(client, rainfall=30.0)
    dry_map = {a["crop"]: a["climate_fit"] for a in dry["alternatives"]}
    wet_map = {a["crop"]: a["climate_fit"] for a in wet["alternatives"]}
    shared = set(dry_map) & set(wet_map)
    assert shared
    assert any(dry_map[c] != wet_map[c] for c in shared), \
        "climate_fit ignored rainfall"


def test_season_changes_the_ranking(client):
    kharif = _answer(client, season="kharif")
    rabi = _answer(client, season="rabi")
    assert [a["crop"] for a in kharif["alternatives"]] != \
           [a["crop"] for a in rabi["alternatives"]] or \
           kharif["alternatives"][0]["season_fit"] != \
           rabi["alternatives"][0]["season_fit"]
