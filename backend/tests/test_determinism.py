"""
Reproducibility: the same question must get the same answer.

A farmer who closes a screen and reopens it, or two farmers on the same soil,
must not see the rank change. Nothing in the decision path may sample, shuffle
or seed itself from the clock - these tests call each scored endpoint twice and
compare the payload field by field.

The one field allowed to differ is the LLM narrative (`icar_advice`), because it
is generated prose; its inputs are pinned (temperature 0, memoised per question)
and everything it cites is checked here instead.
"""
from __future__ import annotations

import json

ENDPOINTS = [
    ("POST /predict", "/predict",
     {"district": "Kolar", "state": "Karnataka", "season": "kharif"}),
    ("POST /predict (rabi)", "/predict",
     {"district": "Ludhiana", "state": "Punjab", "season": "rabi"}),
    ("POST /rotation/suggestions", "/rotation/suggestions",
     {"prev_crop": "Rice", "N": 90, "P": 40, "K": 40, "top_n": 3,
      "district": "Kolar", "state": "Karnataka"}),
    ("POST /rotation/plan", "/rotation/plan",
     {"season1_crop": "Rice", "N": 90, "P": 40, "K": 40, "ph": 6.5,
      "district": "Kolar"}),
    ("POST /location/default-npk", "/location/default-npk",
     {"district": "Kolar", "state": "Karnataka", "mode": "auto"}),
    ("POST /predict/14day", "/predict/14day",
     {"district": "Kolar", "commodity": "Rice", "market": "All"}),
    ("POST /predict/trajectory", "/predict/trajectory",
     {"district": "Kolar", "commodity": "Rice", "market": "All", "days": 30}),
]

GETS = [
    "/market/price?commodity=Rice&district=Kolar&state=Karnataka",
    "/market/history?commodity=Rice&district=Kolar&state=Karnataka&days=30",
    "/weather?district=Kolar&state=Karnataka",
    "/crop/info?crops=Rice",
    "/predict/single?district=Kolar&commodity=Rice&market=All",
    "/predict/factors?commodity=Rice&district=Kolar&state=Karnataka",
    "/commodities",
    "/markets",
]


def _stable(payload):
    return json.dumps(payload, sort_keys=True, default=str)


def test_post_endpoints_are_reproducible(client):
    for label, path, body in ENDPOINTS:
        first = client.post(path, json=body)
        second = client.post(path, json=body)
        assert first.status_code == 200, f"{label}: {first.text[:200]}"
        assert second.status_code == 200, f"{label}: {second.text[:200]}"
        assert _stable(first.json()) == _stable(second.json()), \
            f"{label} changed between identical calls"


def test_get_endpoints_are_reproducible(client):
    for path in GETS:
        first = client.get(path)
        second = client.get(path)
        assert first.status_code == 200, f"{path}: {first.text[:200]}"
        assert _stable(first.json()) == _stable(second.json()), \
            f"{path} changed between identical calls"


def test_fertiliser_decision_is_reproducible(client):
    """Ranking, probability, dose and the cited passages must all repeat."""
    body = {"crop": "Rice", "soil": "Loamy Soil", "N": 120, "P": 40, "K": 40,
            "PH": 6.4, "district": "Kolar", "state": "Karnataka"}
    a = client.post("/fertilizer/recommend", json=body).json()
    b = client.post("/fertilizer/recommend", json=body).json()
    for field in ("recommended_fertilizers", "top_matches", "soil_nutrients",
                  "dose", "model_inputs", "icar_context", "source"):
        assert a.get(field) == b.get(field), f"{field} changed between calls"


def test_advisory_is_memoised_once_it_succeeds(client, monkeypatch):
    """A repeated question must not spend a second LLM call."""
    import fertilizer_rag
    import main

    main._ICAR_ADVISORY_CACHE.clear()
    calls = {"n": 0}
    real = fertilizer_rag.advisory

    def counted(*args, **kwargs):
        calls["n"] += 1
        out = dict(real(*args, **kwargs))
        # Force a "success" so the cache path is exercised regardless of keys.
        out["advice"] = "cached advisory"
        out["provider"] = "test"
        return out

    monkeypatch.setattr(fertilizer_rag, "advisory", counted)
    body = {"crop": "Maize", "soil": "Loamy Soil", "N": 120, "P": 40, "K": 40,
            "PH": 6.5, "district": "Kolar", "state": "Karnataka"}
    first = client.post("/fertilizer/recommend", json=body).json()
    second = client.post("/fertilizer/recommend", json=body).json()
    assert calls["n"] == 1, "the advisory was regenerated for an identical question"
    assert first["icar_advice"] == second["icar_advice"] == "cached advisory"


def test_failed_advisory_is_not_cached(client, monkeypatch):
    """A 429 or a missing key must be retried, not frozen for the process."""
    import fertilizer_rag
    import main

    main._ICAR_ADVISORY_CACHE.clear()
    attempts = {"n": 0}

    def flaky(*args, **kwargs):
        attempts["n"] += 1
        return {"sources": [], "advice": None, "provider": None,
                "note": "quota", "retrieval": "tfidf"}

    monkeypatch.setattr(fertilizer_rag, "advisory", flaky)
    body = {"crop": "Maize", "soil": "Loamy Soil", "N": 120, "P": 40, "K": 40,
            "PH": 6.5, "district": "Kolar", "state": "Karnataka"}
    client.post("/fertilizer/recommend", json=body)
    client.post("/fertilizer/recommend", json=body)
    assert attempts["n"] == 2
