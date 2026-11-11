"""
Tests for the two trained models and the rotation scoring.

These cover the things the reports claim, so the numbers in
reports/crop-model-report.md and reports/fertilizer-model-report.md stay
honest as the code moves: the district model must actually beat the lookup
baseline it replaced, /predict must be serving it, and the rotation scoring
must apply the family and disease-break penalties it documents.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def district_model():
    import district_data

    if not district_data.CROP_MODEL:
        pytest.skip("district crop model not trained - run train_crop_model.py")
    return district_data.CROP_MODEL


@pytest.fixture(scope="module")
def fertilizer_bundle():
    from utils import utils

    if not utils._FERTILIZER_BUNDLE:
        pytest.skip("fertiliser model not trained - run train_fertilizer_model.py")
    return utils._FERTILIZER_BUNDLE


# ─────────────────────── district crop model ─────────────────────────────

def test_district_model_beats_the_lookup_it_replaces(district_model):
    """The whole reason to train this: generalising past a district lookup.

    Selected on grouped precision@3, so that is the number the baseline has to
    lose to. nearest-district P@3 is the app's existing behaviour in spirit.
    """
    metrics = district_model["metrics"][district_model["model_name"]]
    grouped = metrics["grouped_by_district"]
    baseline = district_model["baselines"]["nearest_district"]["precision_at_3"]
    assert grouped["precision_at_3"] > baseline, (
        f"grouped P@3 {grouped['precision_at_3']:.3f} does not beat the "
        f"nearest-district baseline {baseline:.3f}")
    assert grouped["auc"] > 0.9


def test_district_model_knows_real_crops_only(district_model):
    """Aggregate government buckets must never be a predicted class."""
    aggregates = {"total food grains", "cereals", "nutri/coarse cereals",
                  "shree anna /nutri cereals", "other pulses"}
    assert not aggregates & set(district_model["crops"])
    assert "rice" in district_model["crops"]
    assert len(district_model["districts"]) > 100


def test_district_model_loads_no_leaky_outcome_columns(district_model):
    """area / production / yield are consequences of the label, not inputs."""
    assert not {"area", "production", "yield"} & set(district_model["district_features"])


def test_predict_scores_from_the_district_model(client, district_model):
    r = client.post("/predict", json={
        "district": "Kolar", "state": "Karnataka", "season": "kharif"})
    assert r.status_code == 200
    body = r.json()
    top = body["alternatives"][0]
    assert top["ml_source"] == "district"
    assert 0.0 <= top["ml_prob"] <= 1.0
    # Kolar is a ragi district; a place-blind model does not know that.
    assert top["crop"].lower().startswith("ragi"), body["crop"]


def test_unknown_district_still_answers(client):
    """No bundle hit must degrade to the climate model, not to a 500."""
    r = client.post("/predict", json={
        "district": "Nowhere Nagar", "state": "Atlantis", "season": "kharif",
        "N": 90, "P": 40, "K": 40, "temperature": 27, "humidity": 70,
        "rainfall": 5})
    assert r.status_code == 200
    assert r.json()["alternatives"]


def test_model_status_reports_the_measured_numbers(client):
    r = client.get("/model/crop")
    assert r.status_code == 200
    body = r.json()
    assert body["grouped_precision_at_3"] > 0.9
    assert body["districts"] > 100
    assert "nearest_district" in body["baselines"]


# ─────────────────────── rotation scoring ────────────────────────────────

@pytest.fixture(scope="module")
def rotation():
    from utils.utils import get_rotation_suggestions

    return get_rotation_suggestions


def test_rotation_penalties_match_their_flags(rotation):
    """Every penalty reported must equal the rule that fired."""
    for crop in ("Rice", "Wheat", "Maize", "Cotton", "Sugarcane", "Groundnut"):
        result = rotation(crop, 90, 40, 40, top_n=5)
        if "error" in result:
            continue
        for s in result["all_candidates"]:
            expected = (0.15 if s["same_family"] else 0.0) + \
                       (0.30 if s["avoids_previous"] else 0.0)
            assert s["penalty"] == pytest.approx(expected, abs=1e-6)
            assert s["final_score"] <= max(0.0, s["cosine_score"]
                                           + s["n_fix_bonus"] + 0.18)


def test_same_family_repetition_is_demoted(rotation):
    """Two crops of one family back to back must score below the raw fit."""
    from utils.utils import crop_rotation_df

    checked = 0
    for crop in crop_rotation_df["crop"].tolist():
        result = rotation(crop, 90, 40, 40, top_n=30)
        if "error" in result:
            continue
        for s in result["all_candidates"]:
            if s["same_family"]:
                assert s["final_score"] < s["cosine_score"] + s["n_fix_bonus"]
                checked += 1
    assert checked > 0, "no rotation case exercised the family penalty"


def test_district_history_enters_the_ranking(rotation):
    """A district's own yield record must move the score, not just decorate it."""
    plain = rotation("Rice", 90, 40, 40, top_n=5)
    local = rotation("Rice", 90, 40, 40, top_n=5, district="kolar")
    assert all(s["history_score"] == 0 for s in plain["suggestions"])

    def by_crop(result):
        return {s["crop"]: s for s in result["suggestions"]}

    plain_map, local_map = by_crop(plain), by_crop(local)
    shared = set(plain_map) & set(local_map)
    assert shared
    assert any(local_map[c]["history_score"] > 0 for c in shared)
    moved = [c for c in shared
             if local_map[c]["final_score"] != plain_map[c]["final_score"]]
    assert moved, "district history was computed but never changed a score"


def test_rotation_endpoint_accepts_a_district(client):
    r = client.post("/rotation/suggestions", json={
        "prev_crop": "Rice", "N": 90, "P": 40, "K": 40,
        "district": "kolar", "top_n": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["suggestions"]
    assert "history_score" in body["suggestions"][0]
    assert "same_family" in body["suggestions"][0]


# ─────────────────────── fertiliser model ────────────────────────────────

def test_fertilizer_model_beats_cosine_retrieval(fertilizer_bundle):
    m = fertilizer_bundle["metrics"]
    assert m["cv_accuracy"] > m["cosine_baseline_top1"], (
        f"model {m['cv_accuracy']:.3f} does not beat retrieval "
        f"{m['cosine_baseline_top1']:.3f}")
    assert m["cv_accuracy"] > 0.75


def test_fertilizer_scores_are_probabilities(fertilizer_bundle):
    from utils.utils import recommend_fertilizer

    rows = recommend_fertilizer("rice", "loamy soil", 60, 40, 40, 6.5, top_k=5)
    assert rows is not None and len(rows) == 5
    sims = rows["Similarity"].tolist()
    assert all(0.0 <= s <= 1.0 for s in sims)
    assert sims == sorted(sims, reverse=True)
    assert rows["Remark"].iloc[0]


def test_acidic_soil_is_limed_before_fertilised(client):
    """pH 5.2 must lead with lime: the NPK ranking alone would not."""
    r = client.post("/fertilizer/recommend", json={
        "crop": "Rice", "soil": "Loamy", "N": 60, "P": 40, "K": 40, "PH": 5.2})
    assert r.status_code == 200
    body = r.json()
    assert body["recommended_fertilizers"][0] == "Lime"
    assert body["top_matches"][0]["Fertilizer"] == "Lime"


def test_alkaline_soil_gets_gypsum(client):
    r = client.post("/fertilizer/recommend", json={
        "crop": "Wheat", "soil": "Sandy", "N": 40, "P": 30, "K": 20, "PH": 8.8})
    assert r.json()["recommended_fertilizers"][0] == "Gypsum"


def test_neutral_soil_has_no_amendment(client):
    r = client.post("/fertilizer/recommend", json={
        "crop": "Rice", "soil": "Loamy", "N": 60, "P": 40, "K": 40, "PH": 6.8})
    names = r.json()["recommended_fertilizers"]
    assert "Lime" not in names and "Gypsum" not in names


def test_unknown_crop_falls_back_to_the_rules(client):
    """A crop the dataset never saw must still get a transparent answer."""
    r = client.post("/fertilizer/recommend", json={
        "crop": "Dragonfruit", "soil": "Loamy", "N": 20, "P": 10, "K": 10,
        "PH": 6.5})
    assert r.status_code == 200
    assert r.json()["recommended_fertilizers"]
