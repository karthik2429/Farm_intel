"""
Assistant guard tests (Phase 5).

The assistant must never invent a price, never open a link outside the
allowlist, never blow the rate limit, and must degrade honestly when no LLM
key is configured.

Run from the repo root:
    ./collab/venv/bin/python -m pytest Farm_intel/backend/tests -q
"""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import chat  # noqa: E402

CTX = {
    "lang": "en",
    "lang_name": "English",
    "district": "Guntur",
    "state": "Andhra Pradesh",
    "crops": ["Cotton"],
    "season": "kharif",
}


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """No LLM keys, empty cache/quotas for every test."""
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    chat._cache.clear()
    chat._buckets.clear()
    chat._global_bucket.clear()
    yield


# --------------------------------------------------------------- routing ----

def test_price_question_is_answered_from_the_database():
    out = chat.answer("cotton price", CTX, [])
    assert out["source"] == "database"
    assert out["cards"], "a real price answer must carry a price card"
    price_card = out["cards"][0]
    assert price_card["type"] == "price"
    # Either a real number with provenance, or an explicit "not available"
    if price_card["data"].get("price") is not None:
        assert price_card["data"]["is_real"] is True
        assert price_card["data"]["market"]


def test_forecast_question_returns_numbers_or_an_honest_refusal():
    out = chat.answer("banana forecast", CTX, [])
    assert out["reply"]
    # never a fabricated number without a forecast card behind it
    if out["cards"]:
        assert out["cards"][0]["type"] == "forecast"
        assert out["cards"][0]["data"]["mape"] is not None


def test_navigation_question_produces_a_navigate_action():
    out = chat.answer("open the market page", CTX, [])
    assert out["actions"], "navigation must return an in-app action"
    action = out["actions"][0]
    assert action["type"] == "navigate"
    assert action["url"].startswith("/market")


def test_price_question_without_a_crop_asks_for_one():
    out = chat.answer("what is the price today", CTX, [])
    assert "crop" in out["reply"].lower() or "फसल" in out["reply"]


def test_routed_answers_never_need_an_llm(monkeypatch):
    def boom(*_a, **_kw):
        raise AssertionError("the LLM must not be called for a price question")

    monkeypatch.setattr(chat, "call_llm", boom)
    out = chat.answer("cotton price", CTX, [])
    assert out["source"] == "database"


# ------------------------------------------------------------- allowlist ----

def test_open_external_blocks_unknown_hosts():
    result = chat.run_tool("open_external", {"url": "https://evil.example.com"}, CTX)
    assert result.get("error") == "blocked"


def test_open_external_blocks_lookalike_hosts():
    assert not chat.allowed_host("https://pmkisan.gov.in.evil.com")
    assert not chat.allowed_host("javascript:alert(1)")
    assert not chat.allowed_host("http://127.0.0.1/secret")


def test_open_external_allows_government_domains():
    assert chat.allowed_host("https://pmkisan.gov.in")
    assert chat.allowed_host("https://www.agmarknet.gov.in/report")
    result = chat.run_tool("open_external", {"url": "https://pmkisan.gov.in"}, CTX)
    assert result.get("action") == "open_external"
    assert result.get("needs_confirmation") is True


def test_scheme_answers_only_offer_allowlisted_links():
    out = chat.answer("which government scheme can I apply for", CTX, [])
    assert out["actions"]
    for action in out["actions"]:
        assert chat.allowed_host(action["url"]), action["url"]


# ----------------------------------------------------------- rate limits ----

def test_rate_limit_stops_a_user_at_the_configured_cap(monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_USER_PER_HOUR", "3")
    chat._buckets.clear()
    for _ in range(3):
        assert chat.check_rate("user-a") is None
    blocked = chat.check_rate("user-a")
    assert blocked and "limit" in blocked.lower()
    # a different user is unaffected
    assert chat.check_rate("user-b") is None


def test_global_rate_limit_exists(monkeypatch):
    monkeypatch.setattr(chat, "GLOBAL_LIMIT_PER_HOUR", 2)
    chat._global_bucket.clear()
    chat._buckets.clear()
    assert chat.check_rate("u1") is None
    assert chat.check_rate("u2") is None
    assert chat.check_rate("u3") is not None


# --------------------------------------------------------- missing keys -----

def test_open_question_without_any_key_explains_what_is_missing():
    out = chat.answer("how do I improve soil organic matter", CTX, [])
    assert out["source"] == "setup"
    assert "GEMINI_API_KEY" in out["reply"]
    assert out["setup_required"] == ["GEMINI_API_KEY"]
    # and it must not pretend to have answered
    assert not out["cards"]


def test_provider_list_is_empty_without_keys():
    assert chat.providers() == []
    assert chat.configured() is False


# ----------------------------------------------------------------- cache ----

def test_identical_questions_are_served_from_cache():
    first = chat.answer("cotton price", CTX, [])
    second = chat.answer("cotton price", CTX, [])
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["reply"] == first["reply"]


def test_reply_follows_the_requested_language():
    hi = chat.answer("टमाटर का भाव", {**CTX, "lang": "hi", "lang_name": "Hindi"}, [])
    assert any("\u0900" <= ch <= "\u097f" for ch in hi["reply"]), hi["reply"]
