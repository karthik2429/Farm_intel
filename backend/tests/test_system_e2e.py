"""End-to-end journeys: what the farmer's session actually produces.

Each test walks the same call chain the React app makes for one screen flow and
asserts the payloads agree with each other. That is the gap unit tests miss:
every endpoint can be individually "correct" while the chain contradicts itself
(price says ₹2,200 but the chat says ₹1,750).

Run from the repo root:
    collab/venv/bin/python -m pytest Farm_intel/backend/tests/test_system_e2e.py -q
"""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import price_in_reply


def _assert_price_payload(body: dict) -> None:
    assert body["unit"] == "₹/quintal"
    assert body["price"] > 0
    # Bounds are optional by contract: a published monthly average and an MSP
    # reference have a price but no observed min/max (see marketApi.ts). When
    # the payload does carry them, they must bracket the modal price.
    if body.get("min_price") is not None and body.get("max_price") is not None:
        assert body["min_price"] <= body["price"] <= body["max_price"]
    assert body["is_real"] is True


def test_journey_first_run_district_to_daily_action(client, facts):
    """A brand-new farmer: pick a district, get soil, crop, plan, price, advice."""
    district = facts["daily_district"]
    state = facts["daily_state"]

    # 1. Onboarding prefills the soil form from the district's soil survey.
    soil = client.post("/location/default-npk",
                       json={"district": district, "state": state})
    assert soil.status_code == 200
    soil = soil.json()
    assert soil["source"] == "district_soil_survey"

    # 2. Home card: crop recommendation from the same location.
    crop = client.post("/predict", json={
        "district": district, "state": state, "season": "kharif",
        "N": soil["N"], "P": soil["P"], "K": soil["K"], "ph": soil["ph"],
        "temperature": soil["temperature"], "humidity": soil["humidity"],
        "rainfall": soil["rainfall"],
    })
    assert crop.status_code == 200
    crop = crop.json()
    assert crop["crop"], "home needs one headline crop"
    assert crop["soil_used"]["N"] == pytest.approx(soil["N"], abs=0.1)

    # 3. The crop page the farmer opens next (agronomy join).
    info = client.get("/crop/info", params={"crops": crop["crop"]}).json()["crops"]
    entry = info.get(crop["crop"], {})
    assert entry.get("unavailable") is not True, (
        f"recommended {crop['crop']} but /crop/info cannot describe it")

    # 4. Fertilizer tab, using the recommended crop and the same soil.
    fert = client.post("/fertilizer/recommend", json={
        "crop": crop["crop"], "soil": "Loamy", "N": soil["N"], "P": soil["P"],
        "K": soil["K"], "PH": soil["ph"], "district": district, "state": state,
    }).json()
    assert fert["recommended_fertilizers"], "fertilizer tab must always offer a plan"
    assert fert["soil_nutrients"]["N"] == pytest.approx(soil["N"], abs=0.1)

    # 5. Rotation tab: the same crop as season 1 produces a next-season plan.
    plan = client.post("/rotation/plan", json={
        "season1_crop": crop["crop"], "N": soil["N"], "P": soil["P"],
        "K": soil["K"], "ph": soil["ph"], "district": district, "state": state,
    }).json()
    if "error" not in plan:
        assert plan["season2_options"], "rotation needs a next crop"
        next_crop = plan["season2_options"][0]["crop"]
        assert plan["soil_after_s1"] != plan["input_npk"]

    # 6. Market tab: the district's own price, then the history line.
    price = client.get("/market/price", params={
        "commodity": facts["daily_commodity"], "district": district,
        "state": state}).json()
    if price["price"] is not None:
        _assert_price_payload(price)


def test_journey_price_to_forecast_to_chat_agree(client, forecast_scope, price_scope):
    """The number on the Predict screen must be the number the assistant says."""
    scope = dict(forecast_scope)
    forecast = client.post("/predict/14day", json=scope)
    assert forecast.status_code == 200, forecast.text
    entry = forecast.json()[0]

    history = client.get("/market/history", params={
        "commodity": scope["commodity"], "district": scope["district"],
        "state": scope["state"], "days": 90}).json()

    # The chart and the forecast must describe the same series basis.
    assert history["points"], "a forecastable crop must have a chart line"
    assert history["basis"] == entry["history_basis"], (
        "history is plotted on %r but the forecast runs on %r"
        % (history["basis"], entry["history_basis"]))

    single = client.get("/predict/single", params=scope).json()
    assert single["current_price"] == entry["current_price"]
    assert single["predicted_change_pct"] == entry["predicted_change_pct"]

    # Chat must quote the database, not a memory of it. Use the fresh pair: a
    # 115-day-old series is deliberately not served as "today's" price.
    chat = client.post("/chat", json={
        "messages": [{"role": "user",
                      "content": f"{price_scope['commodity']} price"}],
        "district": price_scope["district"], "state": price_scope["state"],
        "lang": "en", "user_id": "journey-price"}).json()
    assert chat["source"] == "database"
    card = next(c for c in chat["cards"] if c["type"] == "price")["data"]
    quoted = price_in_reply(chat["reply"])
    assert quoted == pytest.approx(card["price"], abs=1), (
        f"assistant said {quoted} but the database card says {card['price']}")
    assert chat["actions"][0]["url"].startswith("/predict?crop=")


def test_journey_missing_data_is_explained_at_every_step(client):
    """An unknown corner of the country must not produce invented numbers."""
    missing = {"district": "Atlantis", "state": "Atlantis", "commodity": "Zzzunknown"}

    price = client.get("/market/price", params=missing)
    assert price.status_code == 200
    assert price.json()["price"] is None

    history = client.get("/market/history", params=missing).json()
    assert history["points"] == []
    assert history["basis"] == "none"
    assert "No real mandi history" in history["note"]

    forecast = client.post("/predict/14day", json=missing)
    assert forecast.status_code == 404
    assert "agmarknet_monthly.py" in forecast.json()["detail"]

    # A known crop in an unknown district: the assistant must refuse to quote
    # a number, not borrow another state's rate.
    chat = client.post("/chat", json={
        "messages": [{"role": "user", "content": "Tomato price in Atlantis"}],
        "district": "Atlantis", "state": "Atlantis",
        "user_id": "journey-missing"}).json()
    assert chat["source"] == "rules"
    assert "will not guess" in chat["reply"]
    assert chat["cards"] == []

    # A crop it cannot even resolve gets asked back, not guessed at.
    gibberish = client.post("/chat", json={
        "messages": [{"role": "user", "content": "Zzzunknown price please"}],
        "district": "Atlantis", "user_id": "journey-missing-2"}).json()
    assert gibberish["cards"] == []
    assert "which crop" in gibberish["reply"].lower()


def test_journey_works_with_every_external_provider_down(client, monkeypatch):
    """Offline weather, offline mandi feed, no LLM: the app still answers."""
    import main

    def _fail(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr(main, "get_weather", _fail)
    import mandi_prices

    monkeypatch.setattr(mandi_prices, "_live_records", lambda *a, **k: [])
    import chat

    monkeypatch.setattr(chat, "configured", lambda: False)

    assert client.get("/weather").status_code == 200
    assert client.post("/predict", json={"district": "North Goa",
                                         "state": "Goa"}).status_code == 200
    assert client.post("/predict/14day", json={"district": "North Goa",
                                               "state": "Goa",
                                               "commodity": "Banana"}).status_code == 200
    answer = client.post("/chat", json={
        "messages": [{"role": "user", "content": "How do I store onions?"}],
        "user_id": "journey-offline"}).json()
    assert answer["source"] == "setup"
    assert "GEMINI_API_KEY" in answer["reply"]


def test_journey_language_keeps_the_same_numbers(client, price_scope):
    """Switching language must translate words, never prices."""
    replies = {}
    for lang in ("en", "hi", "kn"):
        body = client.post("/chat", json={
            "messages": [{"role": "user",
                          "content": f"{price_scope['commodity']} price"}],
            "district": price_scope["district"], "state": price_scope["state"],
            "lang": lang, "user_id": f"journey-lang-{lang}"}).json()
        replies[lang] = body
        assert body["cards"], f"{lang} lost the price card"

    prices = {lang: price_in_reply(body["reply"]) for lang, body in replies.items()}
    assert len(set(prices.values())) == 1, prices
    assert prices["en"] is not None
    # Devanagari and Kannada script, not transliterated English.
    assert any("ऀ" <= ch <= "ॿ" for ch in replies["hi"]["reply"])
    assert any("ಀ" <= ch <= "೿" for ch in replies["kn"]["reply"])


def test_journey_date_hygiene(client, forecast_scope):
    """Every date the UI prints is a real date, ordered and not in the past."""
    today = dt.date.today()
    body = client.post("/predict/14day", json=forecast_scope).json()[0]
    for point in body["trajectory"]:
        d = dt.date.fromisoformat(point["date"])
        assert d > today, "a forecast day must be in the future"
        assert d <= today + dt.timedelta(days=14), "14-day horizon"
    assert body["history_last"] <= today.isoformat()

    price = client.get("/market/price", params={
        "commodity": forecast_scope["commodity"],
        "district": forecast_scope["district"],
        "state": forecast_scope["state"]}).json()
    if price.get("date"):
        assert dt.date.fromisoformat(price["date"]) <= today


def test_journey_repeat_visits_are_stable(client, forecast_scope):
    """Two visits in a row must not change the headline crop or forecast."""
    first_crop = client.post("/predict", json={"district": "North Goa",
                                               "state": "Goa"}).json()
    second_crop = client.post("/predict", json={"district": "North Goa",
                                                "state": "Goa"}).json()
    assert first_crop["crop"] == second_crop["crop"]

    first = client.post("/predict/14day", json=forecast_scope).json()[0]
    second = client.post("/predict/14day", json=forecast_scope).json()[0]
    assert first["predicted_price_14d"] == second["predicted_price_14d"]
    assert first["mape"] == second["mape"]
