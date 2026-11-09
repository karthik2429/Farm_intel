"""
Multilingual assistant coverage.

A farmer speaking Kannada, Telugu or Odia is transcribed in their own script.
Before this suite existed, "ಟೊಮೆಟೊ ಬೆಲೆ" answered "which crop?" because the
commodity lookup only knew Latin spellings — that is the regression these tests
lock down.

Run from the repo root:
    python -m pytest Farm_intel/backend/tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import chat  # noqa: E402
import crop_names  # noqa: E402
import mandi_prices  # noqa: E402

# One real sentence per supported language, written the way it would arrive
# from speech recognition. Each must resolve to a price question about tomato.
NATIVE_PRICE_QUESTIONS = [
    ("hi", "टमाटर का भाव क्या है", "Tomato"),
    ("kn", "ಟೊಮೆಟೊ ಬೆಲೆ ಎಷ್ಟು", "Tomato"),
    ("te", "టొమాటో ధర ఎంత", "Tomato"),
    ("ta", "தக்காளி விலை என்ன", "Tomato"),
    ("ml", "തക്കാളി വില എന്താണ്", "Tomato"),
    ("mr", "टोमॅटो भाव काय आहे", "Tomato"),
    ("gu", "ટામેટા ભાવ કેટલો છે", "Tomato"),
    ("bn", "টমেটো দাম কত", "Tomato"),
    ("pa", "ਟਮਾਟਰ ਕੀਮਤ ਕੀ ਹੈ", "Tomato"),
    ("or", "ଟମାଟୋ ଦର କେତେ", "Tomato"),
]

NATIVE_CROP_WORDS = [
    ("टमाटर", "Tomato"), ("प्याज", "Onion"), ("आलू", "Potato"), ("गेहूं", "Wheat"),
    ("ಟೊಮೆಟೊ", "Tomato"), ("ಈರುಳ್ಳಿ", "Onion"), ("ರಾಗಿ", "Ragi"), ("ಹತ್ತಿ", "Cotton"),
    ("టొమాటో", "Tomato"), ("ఉల్లిపాయ", "Onion"), ("మొక్కజొన్న", "Maize"),
    ("தக்காளி", "Tomato"), ("வெங்காயம்", "Onion"), ("கரும்பு", "Sugarcane"),
    ("തക്കാളി", "Tomato"), ("ഉരുളക്കിഴങ്ങ്", "Potato"),
    ("टोमॅटो", "Tomato"), ("कांदा", "Onion"), ("तूर", "Arhar/Tur"),
    ("ટામેટા", "Tomato"), ("ડુંગળી", "Onion"),
    ("টমেটো", "Tomato"), ("আলু", "Potato"),
    ("ਟਮਾਟਰ", "Tomato"), ("ਕਣਕ", "Wheat"),
    ("ଟମାଟୋ", "Tomato"), ("ଆଳୁ", "Potato"),
]


def test_all_eleven_languages_covered():
    """Ten regional scripts plus English, which needs no table."""
    assert crop_names.languages() == 10
    assert len(crop_names.NATIVE_CROPS) >= 200


@pytest.mark.parametrize("word,expected", NATIVE_CROP_WORDS)
def test_native_crop_word_resolves_to_agmarknet_name(word, expected):
    assert mandi_prices.resolve_commodity(word) == expected


def test_native_map_only_uses_english_canonical_names():
    """Every target must be an ASCII commodity name the HTTP layer can fetch."""
    bad = {k: v for k, v in crop_names.NATIVE_CROPS.items() if not v.isascii() or not v.strip()}
    assert not bad


def test_unknown_regional_word_is_not_turned_into_a_commodity():
    """A guess here would show a farmer the price of the wrong crop."""
    assert mandi_prices.resolve_commodity("ಕ್ಷಕ್ಷ") is None
    assert mandi_prices.resolve_commodity("अज्ञातशब्द") is None


def test_english_names_still_resolve_unchanged():
    assert mandi_prices.resolve_commodity("tomato") == "Tomato"
    assert mandi_prices.resolve_commodity("Green Chilli") == "Green Chilli"


@pytest.mark.parametrize("lang,question,crop", NATIVE_PRICE_QUESTIONS)
def test_native_price_question_detects_crop(lang, question, crop):
    intent = chat.detect_intent(question, {"lang": lang})
    assert intent is not None, f"{lang}: no intent for {question!r}"
    assert intent["kind"] == "price"
    assert intent["crop"] == crop


@pytest.mark.parametrize("question,expected_page", [
    ("ಮಾರುಕಟ್ಟೆ ತೆರೆಯಿರಿ", "market"),
    ("मंडी खोलो", "market"),
    ("ବଜାର ଖୋଲ", "market"),
    ("मेरी प्रोफ़ाइल खोलो", "profile"),
    ("ಪ್ರೊಫೈಲ್ ತೋರಿಸು", "profile"),
    ("open the fertilizer page", "fertilizer"),
    ("खाद वाला पेज", "fertilizer"),
    ("கேழ்வரகு சுழற்சி", None),          # a crop name is not a rotation request
    ("बेल फसल चक्र", "rotation"),
    ("எந்த பயிர் விதைக்க", "crops"),
    ("ହୋମ ଖୋଲ", "home"),
])
def test_navigation_intents(question, expected_page):
    intent = chat.detect_intent(question, {"lang": "xx"})
    if expected_page is None:
        assert intent is None or intent.get("page") != "rotation"
        return
    assert intent is not None, question
    assert intent["kind"] == "navigate"
    assert intent["page"] == expected_page


@pytest.mark.parametrize("page", sorted(chat.NAV_PAGES))
def test_every_navigation_target_has_a_real_route(page):
    """No intent may point at a screen the app does not have."""
    result = chat.run_tool("navigate", {"page": page}, {"lang": "en"})
    assert result["action"] == "navigate"
    assert result["url"].startswith("/")
    assert result["url"] != "/", f"{page} fell back to the default route"


def test_agronomy_advice_is_not_refused_by_the_prompt():
    prompt = chat.build_system_prompt({"lang": "en", "lang_name": "English"})
    assert "do not refuse" in prompt.lower()
    assert "general guidance" in prompt.lower()


def test_forecast_intent_from_native_text():
    assert chat.detect_intent("टमाटर का अनुमान", {"lang": "hi"})["kind"] == "forecast"
    assert chat.detect_intent("ଟମାଟୋ ପୂର୍ବାନୁମାନ", {"lang": "or"})["kind"] == "forecast"


def test_every_language_names_every_screen():
    """A nav answer must never fall back to English mid-sentence."""
    assert set(chat.PAGE_NAMES) == set(chat.PHRASES), "every reply language needs screen names"
    for lang in chat.PHRASES:
        assert lang in chat.PAGE_NAMES, lang
        assert set(chat.PAGE_NAMES[lang]) == set(chat.NAV_PAGES), lang
        assert all(name.strip() for name in chat.PAGE_NAMES[lang].values()), lang


@pytest.mark.parametrize("lang,question,expected", [
    ("kn", "ಮಾರುಕಟ್ಟೆ ತೆರೆಯಿರಿ", "ಮಾರುಕಟ್ಟೆ"),
    ("hi", "खाद वाला पेज", "खाद सलाह"),
    ("ta", "எந்த பயிர் விதைக்க", "பயிர் பரிந்துரை"),
])
def test_navigation_reply_is_in_the_farmers_language(lang, question, expected):
    reply = chat.answer(question, {"lang": lang, "lang_name": lang})
    assert expected in reply["reply"]
    assert reply["actions"][0]["label"] == expected
    assert reply["actions"][0]["url"].startswith("/")


# ---------------------------------------------------------------------------
# Gemini adapter: tool results, thought parts, empty-reply retry
# ---------------------------------------------------------------------------
class _StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _reply(text="", calls=None, finish="STOP", thoughts=""):
    parts = []
    if thoughts:
        parts.append({"text": thoughts, "thought": True})
    if text:
        parts.append({"text": text})
    for name in calls or []:
        parts.append({"functionCall": {"name": name, "args": {}}})
    return {"candidates": [{"content": {"parts": parts}, "finishReason": finish}]}


def test_gemini_folds_tool_results_into_the_question_turn(monkeypatch):
    """The tool data must reach the model, or the farmer looks ignored."""
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["body"] = json
        return _StubResponse(_reply(text="Done."))

    monkeypatch.setattr(chat.requests, "post", fake_post)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Should I use urea or DAP?"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "fertilizer_advice"}}]},
        {"role": "tool", "name": "fertilizer_advice", "content": '{"available": false, "note": "no soil card"}'},
    ]
    text, calls, provider = chat._gemini_chat(messages)
    contents = captured["body"]["contents"]
    assert provider == "gemini" and text == "Done." and calls == []
    assert len(contents) == 1, "tool result must not become a second user turn"
    assert contents[0]["role"] == "user"
    joined = " ".join(p["text"] for p in contents[0]["parts"])
    assert "no soil card" in joined and "Should I use urea or DAP?" in joined


def test_gemini_never_shows_thought_parts(monkeypatch):
    monkeypatch.setattr(chat.requests, "post",
                        lambda *a, **k: _StubResponse(_reply(text="Visible answer.",
                                                            thoughts="secret reasoning")))
    text, _, _ = chat._gemini_chat([{"role": "user", "content": "hi"}])
    assert text == "Visible answer."
    assert "secret reasoning" not in text


def test_gemini_requests_low_thinking_and_extra_output_room(monkeypatch):
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["body"] = json
        return _StubResponse(_reply(text="ok"))

    monkeypatch.setattr(chat.requests, "post", fake_post)
    chat._gemini_chat([{"role": "user", "content": "hi"}])
    gen = captured["body"]["generationConfig"]
    assert gen["thinkingConfig"]["thinkingLevel"] == "low"
    assert gen["maxOutputTokens"] >= 900


def test_gemini_retries_without_tools_when_reply_is_empty(monkeypatch):
    """MALFORMED_FUNCTION_CALL used to surface as "all providers failed"."""
    bodies = []

    def fake_post(url, params=None, json=None, timeout=None):
        bodies.append(json)
        if len(bodies) == 1:
            return _StubResponse(_reply(finish="MALFORMED_FUNCTION_CALL"))
        return _StubResponse(_reply(text="Plain answer."))

    monkeypatch.setattr(chat.requests, "post", fake_post)
    tools = chat.TOOL_SCHEMAS
    text, _, _ = chat._gemini_chat([{"role": "user", "content": "hi"}], tools)
    assert text == "Plain answer."
    assert "tools" in bodies[0]
    assert "tools" not in bodies[1]
    assert "Do not call any tool" in bodies[1]["systemInstruction"]["parts"][0]["text"]
