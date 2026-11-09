"""API contract, input-validation and failure-mode tests.

These call the real FastAPI app through TestClient with the models loaded, so
they assert what a client actually receives: status codes, JSON shapes and the
honesty of every fallback. Outbound HTTP is blocked by the conftest harness, so
"passes offline" means "degrades honestly when providers are down".

Run from the repo root:
    collab/venv/bin/python -m pytest Farm_intel/backend/tests/test_system_api.py -q
"""
from __future__ import annotations

import datetime as dt
import math

import pytest

import price_forecast

pytestmark = pytest.mark.usefixtures("reset_runtime_state")


# ---------------------------------------------------------------------------
# Health / configuration
# ---------------------------------------------------------------------------
def test_health_reports_real_model_state(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    # The crop model must actually be loaded, not just claimed.
    assert "rf_crop" in body["models_loaded"]
    assert isinstance(body["price_model"], bool)
    assert body["version"]


def test_config_status_never_leaks_secret_values(client):
    body = client.get("/config/status").json()
    assert set(body["configured"]) and all(
        isinstance(v, bool) for v in body["configured"].values())
    # Only booleans and public facts — no key material anywhere in the payload.
    flat = str(body).lower()
    for forbidden in ("sk-", "aiza", "gsk_", "service_key", "password", "token="):
        assert forbidden not in flat


# ---------------------------------------------------------------------------
# Crop recommendation
# ---------------------------------------------------------------------------
def test_crop_recommendation_contract(client, facts):
    r = client.post("/predict", json={"district": facts["daily_district"],
                                      "state": facts["daily_state"],
                                      "season": "kharif"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["crop"], str) and body["crop"]
    assert 0.0 < body["confidence"] <= 1.0
    alts = body["alternatives"]
    assert 1 <= len(alts) <= 4
    assert alts[0]["crop"] == body["crop"], "top alternative must be the recommendation"
    scores = [a["confidence"] for a in alts]
    assert scores == sorted(scores, reverse=True), "alternatives must be ranked"
    assert all(0 < s <= 1 for s in scores)
    assert 1 <= len(body["Top Crops"]) <= 3
    assert body["soil_used"]["N"] >= 0 and 0 <= body["soil_used"]["ph"] <= 14
    assert body["weather"]["humidity"] <= 100


def test_crop_recommendation_accepts_coordinates(client):
    r = client.post("/predict", json={"lat": 12.97, "lon": 77.59, "mode": "coords",
                                      "N": 120, "P": 60, "K": 80, "ph": 6.8})
    assert r.status_code == 200
    body = r.json()
    assert body["crop"]
    # Supplied soil must be echoed, not silently replaced by district defaults.
    assert body["soil_used"]["N"] == pytest.approx(120, abs=0.1)
    assert body["soil_used"]["ph"] == pytest.approx(6.8, abs=0.1)


def test_crop_recommendation_is_deterministic(client, facts):
    payload = {"district": facts["daily_district"], "state": facts["daily_state"],
               "N": 90, "P": 40, "K": 40, "ph": 6.5,
               "temperature": 28, "humidity": 70, "rainfall": 5}
    first = client.post("/predict", json=payload).json()
    second = client.post("/predict", json=payload).json()
    assert first["crop"] == second["crop"]
    assert first["confidence"] == second["confidence"]


# ---------------------------------------------------------------------------
# Rotation & fertilizer
# ---------------------------------------------------------------------------
def test_rotation_suggestions_contract(client):
    r = client.post("/rotation/suggestions",
                    json={"prev_crop": "Rice", "N": 90, "P": 40, "K": 40, "top_n": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["season1_crop"].lower() == "rice"
    assert len(body["suggestions"]) <= 3
    for s in body["suggestions"]:
        assert s["crop"] and s["family"]
        # NPK depletion never adds nutrients back, and gaps are non-negative.
        assert s["N_gap"] >= 0 and s["P_gap"] >= 0 and s["K_gap"] >= 0
        assert 0.0 <= s["final_score"] <= 1.5
    # A legume (nitrogen fixer) should be among the options after a cereal.
    assert any(s["nitrogen_fixing"] for s in body["suggestions"])


def test_rotation_plan_contract(client):
    r = client.post("/rotation/plan",
                    json={"season1_crop": "Rice", "N": 90, "P": 40, "K": 40,
                          "district": "North Goa", "state": "Goa"})
    assert r.status_code == 200
    body = r.json()
    assert "error" not in body
    # season1 is the crop label; the scored options are season2_options.
    assert body["season1"].lower() == "rice"
    assert body["season2_options"], "a two-season plan needs options"
    assert body["season2_best"] == body["season2_options"][0]["crop"]
    assert body["soil_after_s1"]["N"] < 90, "a cereal must deplete nitrogen"
    assert isinstance(body["warnings"], list)


def test_fertilizer_dataset_contract(client):
    r = client.post("/fertilizer/recommend",
                    json={"crop": "Rice", "soil": "Loamy", "N": 20, "P": 10, "K": 10,
                          "PH": 6.5})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] in ("dataset", "rule_based")
    assert body["recommended_fertilizers"]
    assert body["soil_nutrients"] == {"N": 20.0, "P": 10.0, "K": 10.0, "PH": 6.5}
    # A nitrogen-starved paddy field must be told about a nitrogen source.
    joined = " ".join(body["recommended_fertilizers"]).lower()
    assert any(k in joined for k in ("urea", "dap", "npk", "ammonium"))


def test_fertilizer_handles_unknown_crop_with_rules(client):
    r = client.post("/fertilizer/recommend",
                    json={"crop": "Dragonfruit", "soil": "Red",
                          "N": 10, "P": 5, "K": 5, "PH": 5.0})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rule_based"
    assert any("lime" in f.lower() for f in body["recommended_fertilizers"]), \
        "pH 5.0 must trigger a lime recommendation"


def test_default_npk_uses_district_soil_survey(client):
    r = client.post("/location/default-npk",
                    json={"district": "North Goa", "state": "Goa"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "district_soil_survey"
    assert 0 < body["N"] < 600 and 0 < body["P"] < 300 and 0 < body["K"] < 600
    assert 3.0 <= body["ph"] <= 10.0


# ---------------------------------------------------------------------------
# Market prices
# ---------------------------------------------------------------------------
def test_market_price_contract(client, price_scope):
    r = client.get("/market/price", params=price_scope)
    assert r.status_code == 200
    body = r.json()
    assert body["price"] and body["price"] > 0
    assert body["unit"] == "₹/quintal"
    assert body["is_real"] is True
    d = dt.date.fromisoformat(body["date"])
    assert d <= dt.date.today()
    assert (dt.date.today() - d).days <= 45, "a 'today' price must be fresh"
    assert body["market"]


def test_market_price_is_honest_when_no_data(client):
    r = client.get("/market/price",
                   params={"commodity": "Zzzunknowncrop", "district": "Nowhere"})
    assert r.status_code == 200, "an empty mandi must not 404 the market screen"
    body = r.json()
    assert body["price"] is None
    assert body["source"] == "unavailable"
    assert body["is_real"] is False
    assert "nothing is guessed" in body["detail"]


def test_market_price_bounds_are_ordered(client, price_scope):
    body = client.get("/market/price", params=price_scope).json()
    assert body["min_price"] <= body["price"] <= body["max_price"]


def test_market_status_and_coverage_contract(client):
    status = client.get("/market/status").json()
    assert status["coverage"]["rows"] > 0
    assert status["monthly"]["coverage"]["rows"] >= 0

    cov = client.get("/market/coverage", params={"commodity": "Banana", "limit": 3}).json()
    assert cov["rows"], "Banana has real history in the store"
    assert len(cov["rows"]) <= 3
    for row in cov["rows"]:
        assert row["obs"] > 0
        assert row["first_date"] <= row["last_date"]


def test_market_history_is_sorted_and_clamped(client, price_scope):
    body = client.get("/market/history",
                      params={**price_scope, "days": 0}).json()
    assert body["days"] == 7, "days must be clamped up to a readable window"
    pts = body["points"]
    assert pts, "a fresh pair must have a history line"
    dates = [p["date"] for p in pts]
    assert dates == sorted(dates)
    assert all(p["price"] > 0 for p in pts)
    assert body["basis"] in ("daily", "monthly")

    too_big = client.get("/market/history",
                         params={**price_scope, "days": 9999}).json()
    assert too_big["days"] == 365


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def test_weather_contract(client):
    body = client.get("/weather", params={"district": "North Goa", "state": "Goa"}).json()
    for key in ("district", "state", "temperature", "humidity", "rainfall", "source"):
        assert key in body
    assert -20 <= body["temperature"] <= 60
    assert 0 <= body["humidity"] <= 100
    assert body["rainfall"] >= 0


def test_weather_provider_is_cached_per_location(monkeypatch):
    """Repeat requests must not pay the 800 ms provider round-trip."""
    from utils import utils as utils_module

    calls = []

    class _Fake:
        def json(self):
            return {"current_weather": {"temperature": 29.1, "time": "2026-11-03T10:00"},
                    "hourly": {"time": ["2026-11-03T10:00"],
                               "relativehumidity_2m": [64], "precipitation": [0.0]}}

    def fake_get(url, timeout=None):
        calls.append(url)
        return _Fake()

    monkeypatch.setattr(utils_module.requests, "get", fake_get)
    first = utils_module.get_weather(15.5, 73.83)
    second = utils_module.get_weather(15.501, 73.831)  # rounds into the same cell
    third = utils_module.get_weather(19.07, 72.87)   # different city
    assert first == second == (29.1, 64, 0.0)
    assert len(calls) == 2, f"expected one provider call per location, got {calls}"
    assert third == first


def test_weather_forecast_is_cached_and_skips_empty_results(monkeypatch):
    """The 14-day forecast feeds two screens; it must not refetch per view."""
    from utils import utils as utils_module

    calls = []
    payload = {"daily": {"time": ["2026-11-04"], "temperature_2m_max": [31.0],
                          "temperature_2m_min": [21.0], "precipitation_sum": [0.0],
                          "relative_humidity_2m_max": [70]}}

    class _Fake:
        def json(self):
            return payload

    def fake_get(url, timeout=None):
        calls.append(url)
        return _Fake()

    monkeypatch.setattr(utils_module.requests, "get", fake_get)
    assert utils_module.get_weather_forecast(15.5, 73.83)[0]["temp_max"] == 31.0
    assert utils_module.get_weather_forecast(15.5, 73.83)[0]["temp_max"] == 31.0
    assert len(calls) == 1

    # A failure returns [] and must be retried, not memoised.
    monkeypatch.setattr(utils_module.requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert utils_module.get_weather_forecast(20.0, 77.0) == []
    monkeypatch.setattr(utils_module.requests, "get", fake_get)
    assert utils_module.get_weather_forecast(20.0, 77.0), "empty result was cached"


def test_failed_weather_is_not_cached(monkeypatch):
    """A provider error must not be remembered as today's weather."""
    from utils import utils as utils_module

    state = {"fail": True, "calls": 0}

    class _Fake:
        def json(self):
            return {"current_weather": {"temperature": 31.0, "time": "2026-11-03T10:00"},
                    "hourly": {"time": ["2026-11-03T10:00"],
                               "relativehumidity_2m": [50], "precipitation": [1.5]}}

    def flaky_get(url, timeout=None):
        state["calls"] += 1
        if state["fail"]:
            raise RuntimeError("provider down")
        return _Fake()

    monkeypatch.setattr(utils_module.requests, "get", flaky_get)
    with pytest.raises(RuntimeError):
        utils_module.get_weather(20.0, 77.0)
    state["fail"] = False
    assert utils_module.get_weather(20.0, 77.0) == (31.0, 50, 1.5)
    assert state["calls"] == 2


def test_weather_failure_is_labelled_honestly(client, monkeypatch):
    """Provider down must not be reported as a live Open-Meteo reading."""
    import main

    def _boom(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(main, "get_weather", _boom)
    body = client.get("/weather",
                      params={"district": "North Goa", "state": "Goa"}).json()
    assert body["source"] == "national_fallback", (
        "fallback numbers were labelled as live weather: %r" % body["source"])
    assert -20 <= body["temperature"] <= 60


# ---------------------------------------------------------------------------
# Crop agronomy data
# ---------------------------------------------------------------------------
def test_crop_info_contract_and_unknown_flag(client):
    body = client.get("/crop/info", params={"crops": "Rice,Tomato,Zzzunknown"}).json()
    crops = body["crops"]
    assert "Rice" in crops and "Tomato" in crops
    rice = crops["Rice"]
    assert rice["duration_days"][0] <= rice["duration_days"][1]
    lo, hi = [float(x) for x in rice["ph_range"].replace("–", "-").split("-")]
    assert 0 <= lo <= hi <= 14
    assert rice["ideal_npk"]["N"] > 0
    # Unknown crop must be flagged, never filled with invented agronomy.
    unknown = crops.get("Zzzunknown")
    assert unknown is None or unknown.get("unavailable") is True
    if unknown:
        # No invented agronomy for a crop we do not actually know.
        assert unknown["duration_days"] is None
        assert unknown["yield_t_ha"] is None


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------
def _forecast(client, scope):
    return client.post("/predict/14day", json=scope)


def test_forecast_14day_contract(client, forecast_scope):
    r = _forecast(client, forecast_scope)
    assert r.status_code == 200, r.text
    entries = r.json()
    assert isinstance(entries, list) and len(entries) == 1
    e = entries[0]
    traj = e["trajectory"]
    assert len(traj) == 14
    assert [p["day"] for p in traj] == list(range(1, 15))
    dates = [p["date"] for p in traj]
    assert dates == sorted(dates)
    for p in traj:
        assert p["ci_low"] <= p["predicted_price"] <= p["ci_high"]
        assert p["predicted_price"] > 0
        assert "change_from_prev_pct" in p
    assert e["ci_low_14d"] == traj[-1]["ci_low"]
    assert e["ci_high_14d"] == traj[-1]["ci_high"]
    assert e["predicted_price_14d"] == traj[-1]["predicted_price"]
    assert e["history_basis"] in ("daily", "monthly")
    assert 0 <= e["mape"] <= 100
    assert e["stale_days"] >= 0


def test_forecast_refuses_with_an_actionable_404(client):
    r = _forecast(client, {"district": "Nowhere", "commodity": "Zzzunknown"})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "Not enough real mandi history" in detail
    assert "run agmarknet_monthly.py" in detail, "an error must say how to fix it"


def test_single_prediction_contract(client, forecast_scope):
    r = client.get("/predict/single", params=forecast_scope)
    assert r.status_code == 200
    body = r.json()
    assert 50.0 <= body["confidence"] <= 95.0
    assert body["model"] == "mandi-forecast-v2"
    # The served model is chosen per series and must say which one it used.
    assert body["model_used"] in price_forecast.MODELS
    assert set(body["model_scores"]) <= set(price_forecast.MODELS)
    assert "repaired_rows" in body["data_quality"]
    assert body["signal"]
    assert body["signal"] == body["signal"].strip()
    assert body["factors"]["context"]["signals"]


def test_prediction_factors_carry_evidence(client, forecast_scope):
    body = client.get("/predict/factors", params=forecast_scope).json()
    assert body["signals"], "the factors card needs at least one signal"
    for sig in body["signals"]:
        assert sig["direction"] in ("up", "down", "neutral")
        assert sig["strength"] in ("low", "medium", "high")
        assert len(sig["detail"]) > 20, "a factor without evidence is a guess"
        assert not math.isnan(float(body["up_count"]))


# ---------------------------------------------------------------------------
# Catalogues
# ---------------------------------------------------------------------------
def test_scoped_commodities_are_a_subset(client, price_scope):
    everything = set(client.get("/commodities").json()["commodities"])
    scoped = client.get("/commodities",
                        params={"district": price_scope["district"],
                                "state": price_scope["state"]}).json()
    assert scoped["scope"] == "district"
    assert set(scoped["commodities"]) <= everything
    assert price_scope["commodity"] in scoped["commodities"]


@pytest.mark.xfail(
    strict=True,
    reason=("known defect: AGMARKNET district names with trailing spaces are not "
            "normalized, so scoped catalogue/price lookups miss their rows"),
)
def test_scoped_lookup_survives_trailing_space_district_names(client):
    import price_store

    with price_store._connect() as conn:
        row = conn.execute(
            "SELECT state, district, commodity FROM mandi_prices "
            "WHERE district != trim(district) AND modal_price > 0 LIMIT 1"
        ).fetchone()
    if not row:
        pytest.skip("the store currently has no untrimmed district name")
    listed = price_store.distinct_commodities(row["district"], row["state"])
    assert row["commodity"] in listed


def test_district_catalogue_still_offers_state_crops(client):
    """A district that reports one crop must not hide the rest of the state.

    Tumakuru reports Rice only, but a farmer there still wants coconut, ragi
    and tomato — served from elsewhere in Karnataka and labelled as such.
    """
    body = client.get("/commodities",
                      params={"district": "Tumakuru",
                              "state": "Karnataka"}).json()
    local = body.get("district_commodities") or []
    assert local, "the district's own crops must be identified"
    assert set(local) <= set(body["commodities"])
    assert len(body["commodities"]) > len(local), \
        "the catalogue should also carry the state's crops"


def test_qualified_commodity_name_resolves_to_the_stored_spelling():
    """"Ragi" must not miss "Ragi(Finger Millet)" and fall back to MSP."""
    import mandi_prices

    import price_store

    names = price_store.distinct_commodities()
    stored = {n.strip().lower() for n in names}
    qualified = [n for n in names if "(" in n]
    if not qualified:
        pytest.skip("no qualified commodity names in the store")
    for name in qualified[:8]:
        # A stored spelling is passed through untouched.
        assert mandi_prices.resolve_commodity(name) == name
        bare = name.split("(")[0].strip()
        # Only the unambiguous case is a promise: when exactly one stored name
        # starts with the bare word, the store lookup must widen to it.
        # "Bengal Gram" matches several real commodities, so refusing is right.
        prefix = bare.lower().replace(" ", "")
        cands = [n for n in names
                 if n.strip().lower().replace(" ", "").startswith(prefix)]
        if len(cands) == 1:
            assert mandi_prices.clamp_to_store(bare) == cands[0], \
                f"{bare!r} did not widen to its only stored match {cands[0]!r}"

    # The specific defect: Ragi is stored only as "Ragi(Finger Millet)", so a
    # bare "Ragi" lookup used to miss every row and serve the MSP instead.
    ragi = [n for n in names if n.lower().startswith("ragi")]
    if ragi:
        assert mandi_prices.clamp_to_store("Ragi") in ragi
        price = mandi_prices.get_price("Ragi", "Tumakuru", "Karnataka")
        assert price, "Ragi has no price at all"
        assert price["source"] != "msp_reference", \
            f"bare Ragi fell back to MSP: {price}"


def test_price_for_untraded_crop_states_its_age_and_source(client):
    """A crop the district did not trade today still gets the latest real rate,
    labelled with the district it came from and how old it is."""
    r = client.get("/market/price", params={"commodity": "Coconut",
                                            "district": "Tumakuru",
                                            "state": "Karnataka"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("price"), "a real coconut rate exists somewhere in Karnataka"
    assert body["requested_district"] == "Tumakuru"
    assert body["source_district"]
    assert body["scope"] in ("district", "state")
    assert body["days_old"] is None or body["days_old"] >= 0


def test_markets_are_filtered_by_district(client, price_scope):
    scoped = client.get("/markets", params={"district": price_scope["district"]}).json()
    assert scoped["markets"]
    assert all(m["district"].lower() == price_scope["district"].lower()
               for m in scoped["markets"])


def test_official_district_spelling_finds_the_stored_district(client):
    """"Davanagere" (the name the app ships) is filed as "Davangere" by
    AGMARKNET. Asking under the official spelling used to return no mandis and
    a state-wide crop list; both spellings must describe the same district."""
    params = {"state": "Karnataka", "strict": 1}
    official = client.get("/commodities", params={**params, "district": "Davanagere"}).json()
    stored = client.get("/commodities", params={**params, "district": "Davangere"}).json()
    if not stored["commodities"]:
        pytest.skip("the store has no Davangere rows")

    assert official["commodities"] == stored["commodities"], \
        "the official spelling listed different crops than the stored one"
    assert official["scope"] == "district"
    # The district page names its own mandis, whichever spelling was asked.
    assert official["markets"] == stored["markets"]
    assert client.get("/markets", params={"district": "Davanagere"}).json()["markets"]


def test_strict_district_lists_only_its_own_crops_and_mandis(client):
    """A strict district page is exactly one district: the crop list is the
    district's own, and every mandi named belongs to it."""
    body = client.get("/commodities", params={"district": "Davangere",
                                              "state": "Karnataka",
                                              "strict": 1}).json()
    if not body["commodities"]:
        pytest.skip("the store has no Davangere rows")
    assert body["scope"] == "district"
    assert set(body["commodities"]) == set(body["district_commodities"])
    markets = client.get("/markets", params={"district": "Davangere",
                                             "state": "Karnataka"}).json()["markets"]
    assert markets
    assert all(m["district"].lower() in ("davangere", "davanagere")
               for m in markets)


# ---------------------------------------------------------------------------
# Chat contract
# ---------------------------------------------------------------------------
def test_chat_contract(client):
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "Tomato price?"}],
                                   "district": "Kolar", "lang": "en",
                                   "user_id": "contract-test"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["reply"], str) and body["reply"].strip()
    assert isinstance(body["cards"], list)
    assert isinstance(body["actions"], list)
    assert body["providers_available"] is not None
    assert body["rate_limit_per_hour"] > 0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method,path,payload", [
    ("get", "/market/price", None),
    ("post", "/rotation/suggestions", {"N": 1, "P": 1, "K": 1}),
    ("post", "/rotation/plan", {}),
    ("post", "/fertilizer/recommend", {"soil": "loamy"}),
    ("get", "/predict/single", None),
])
def test_missing_required_fields_return_422(client, method, path, payload):
    r = getattr(client, method)(path, **({} if payload is None else {"json": payload}))
    assert r.status_code == 422, f"{path} accepted a request without required fields"
    assert "detail" in r.json()


def test_wrong_types_return_422(client):
    r = client.post("/predict", json={"N": "not-a-number"})
    assert r.status_code == 422
    r = client.post("/rotation/suggestions",
                    json={"prev_crop": "Rice", "N": "high", "P": 1, "K": 1})
    assert r.status_code == 422


def test_empty_chat_is_rejected(client):
    assert client.post("/chat", json={"messages": []}).status_code == 422
    assert client.post("/chat", json={"messages": [{"role": "user",
                                                     "content": "   "}]}).status_code == 422


def test_unknown_language_falls_back_to_english(client):
    body = client.post("/chat", json={"messages": [{"role": "user", "content": "Tomato price"}],
                                      "district": "Kolar", "lang": "xx",
                                      "user_id": "lang-test"}).json()
    # Hindi/Kannada etc. produce native script; an unknown code must not.
    assert "₹" in body["reply"] or "crop" in body["reply"].lower()


def test_oversized_message_is_truncated_not_rejected(client):
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "tomato " * 5000}],
                                   "district": "Kolar", "user_id": "long-test"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
def test_llm_outage_returns_helpful_message(client, monkeypatch, chat_module):
    def _no_llm(*_a, **_k):
        raise RuntimeError("429 from every provider")

    monkeypatch.setattr(chat_module, "call_llm", _no_llm)
    monkeypatch.setattr(chat_module, "configured", lambda: True)
    body = client.post("/chat", json={
        "messages": [{"role": "user", "content": "How do I store onions for six months?"}],
        "district": "Nashik", "user_id": "outage-test"}).json()
    assert body["source"] == "error"
    assert "temporarily unavailable" in body["reply"].lower()
    assert "tomato price" in body["reply"].lower(), \
        "an outage message must offer the path that still works"


def test_price_store_failure_does_not_500_coverage(client, monkeypatch, store):
    def _boom(*_a, **_k):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(store, "_connect", _boom)
    r = client.get("/market/coverage")
    assert r.status_code == 200
    assert "Store unavailable" in r.json()["note"]


def test_mandi_live_outage_still_serves_stored_price(client, monkeypatch, price_scope):
    import mandi_prices

    monkeypatch.setattr(mandi_prices, "_live_records", lambda *a, **k: [])
    body = client.get("/market/price", params=price_scope).json()
    assert body["price"] > 0
    assert body["source"].startswith("cache_")


def test_xgboost_engine_absence_does_not_break_forecasts(client, monkeypatch):
    """The old Goa engine is optional; forecasts come from the store."""
    import price_engine

    monkeypatch.setattr(price_engine, "model_loaded", lambda: False)
    body = client.get("/market/status").json()
    assert body["coverage"]["rows"] > 0


def test_rate_limit_returns_429_with_a_wait_message(client, chat_module):
    limit = chat_module.settings.chat_rate_limit_per_user_per_hour
    # Pre-fill this user's bucket: the limiter is in-memory by design.
    chat_module._buckets["rl-test"] = [__import__("time").time()] * limit
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "Tomato price"}],
                                   "district": "Kolar", "user_id": "rl-test"})
    assert r.status_code == 429
    detail = r.json()["detail"].lower()
    assert "limit" in detail and "try again" in detail
