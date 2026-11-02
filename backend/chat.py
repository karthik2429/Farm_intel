"""
Kisan assistant backend (Phase 5).

Design goals, in order:
  1. Never invent a price. Price, forecast and navigation questions are
     answered straight from the mandi database — no LLM involved.
  2. Only phrase free-form advice with a free LLM, in the farmer's language.
  3. Degrade honestly: with no key configured the assistant still answers
     price/forecast/navigation questions and says exactly what is missing.

Provider chain (all free tiers, tried in order, falling through on 429/5xx):
    Gemini -> Groq -> OpenRouter -> Ollama (only when OLLAMA_BASE_URL is set)

Tools the model may call:
    get_mandi_prices, get_price_forecast, recommend_crops, fertilizer_advice,
    rotation_plan, navigate, open_external (allowlist-only)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from config import settings

logger = logging.getLogger("farmintel.chat")

TIMEOUT_S = 45
GLOBAL_LIMIT_PER_HOUR = 300

# ---------------------------------------------------------------------------
# Rate limiting (in-memory; resets on restart, which is fine for one worker)
# ---------------------------------------------------------------------------
_buckets: Dict[str, List[float]] = {}
_global_bucket: List[float] = []


def _prune(bucket: List[float], window_s: int = 3600) -> List[float]:
    cut = time.time() - window_s
    return [t for t in bucket if t > cut]


def check_rate(user_id: str) -> Optional[str]:
    """Return a friendly error when the caller is over quota, else None."""
    global _global_bucket
    _global_bucket = _prune(_global_bucket)
    if len(_global_bucket) >= GLOBAL_LIMIT_PER_HOUR:
        return ("The assistant is very busy right now. "
                "Please try again in a few minutes.")

    key = user_id or "anonymous"
    bucket = _prune(_buckets.get(key, []))
    if len(bucket) >= settings.chat_rate_limit_per_user_per_hour:
        _buckets[key] = bucket
        return (f"You have reached the limit of "
                f"{settings.chat_rate_limit_per_user_per_hour} messages per hour. "
                "Try again in a little while.")
    now = time.time()
    bucket.append(now)
    _buckets[key] = bucket
    _global_bucket.append(now)
    return None


# ---------------------------------------------------------------------------
# Answer cache
# ---------------------------------------------------------------------------
_cache: Dict[str, Tuple[float, dict]] = {}


def _cache_key(question: str, lang: str, district: Optional[str]) -> str:
    day = time.strftime("%Y-%m-%d")
    raw = f"{question.strip().lower()}|{lang}|{(district or '').lower()}|{day}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[dict]:
    hit = _cache.get(key)
    if not hit:
        return None
    ts, value = hit
    if time.time() - ts > settings.chat_cache_ttl_hours * 3600:
        _cache.pop(key, None)
        return None
    return value


def _cache_put(key: str, value: dict) -> None:
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def providers() -> List[str]:
    chain = []
    if settings.gemini_api_key:
        chain.append("gemini")
    if settings.groq_api_key:
        chain.append("groq")
    if settings.openrouter_api_key:
        chain.append("openrouter")
    if settings.ollama_base_url:
        chain.append("ollama")
    return chain


def configured() -> bool:
    return bool(providers())


SETUP_HINT = (
    "For open questions I need one free LLM key. Add GEMINI_API_KEY "
    "(free at https://aistudio.google.com/apikey) to Farm_intel/.env and "
    "restart the backend. Price, forecast and navigation questions already "
    "work without it."
)

OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1", "groq_api_key", "groq_model"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key", "openrouter_model"),
    "ollama": (None, None, "ollama_model"),
}


def _openai_style_chat(
    provider: str,
    messages: List[dict],
    tools: Optional[List[dict]] = None,
) -> Tuple[str, List[dict], str]:
    """One round-trip to an OpenAI-compatible endpoint."""
    if provider == "ollama":
        base = settings.ollama_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        key = "ollama"
        model = settings.ollama_model
    else:
        base_tpl, key_attr, model_attr = OPENAI_COMPATIBLE[provider]
        base = base_tpl
        key = getattr(settings, key_attr)
        model = getattr(settings, model_attr)

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": settings.chat_max_output_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    res = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=TIMEOUT_S,
    )
    if res.status_code != 200:
        raise RuntimeError(f"{provider} HTTP {res.status_code}: {res.text[:200]}")
    data = res.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return msg.get("content") or "", msg.get("tool_calls") or [], provider


def _gemini_chat(
    messages: List[dict],
    tools: Optional[List[dict]] = None,
) -> Tuple[str, List[dict], str]:
    """Gemini generateContent with optional function declarations."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] in ("user", "assistant", "model")
    ]
    body: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": settings.chat_max_output_tokens,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"functionDeclarations": [_gemini_decl(t) for t in tools]}]

    res = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json=body,
        timeout=TIMEOUT_S,
    )
    if res.status_code != 200:
        raise RuntimeError(f"gemini HTTP {res.status_code}: {res.text[:200]}")
    data = res.json()
    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    calls = []
    for p in parts:
        fn = p.get("functionCall")
        if fn:
            calls.append({"function": {"name": fn.get("name"), "arguments": json.dumps(fn.get("args") or {})}})
    return text, calls, "gemini"


def _gemini_decl(tool: dict) -> dict:
    fn = tool.get("function", {})
    params = fn.get("parameters") or {"type": "object", "properties": {}}
    # Gemini rejects "additionalProperties" and lowercase type names are fine.
    params = json.loads(json.dumps(params).replace('"additionalProperties": false', '"additionalProperties": false'))
    return {"name": fn.get("name"), "description": fn.get("description"), "parameters": params}


def call_llm(messages: List[dict], tools: Optional[List[dict]] = None) -> Tuple[str, List[dict], str]:
    """Try each configured provider in order. Raises RuntimeError if all fail."""
    last: Optional[Exception] = None
    for provider in providers():
        try:
            if provider == "gemini":
                return _gemini_chat(messages, tools)
            return _openai_style_chat(provider, messages, tools)
        except Exception as exc:  # noqa: BLE001 - fall through to the next provider
            logger.warning("provider %s failed: %s", provider, exc)
            last = exc
    raise RuntimeError(str(last) if last else "No LLM provider configured")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_mandi_prices",
            "description": "Real AGMARKNET modal price for a commodity in a district. Returns null price when there is no real record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commodity": {"type": "string"},
                    "district": {"type": "string"},
                },
                "required": ["commodity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_forecast",
            "description": "14-day Holt-Winters price forecast with confidence band for a commodity.",
            "parameters": {
                "type": "object",
                "properties": {"commodity": {"type": "string"}, "market": {"type": "string"}},
                "required": ["commodity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_crops",
            "description": "Rank crops for the farmer's soil, season and district.",
            "parameters": {
                "type": "object",
                "properties": {"season": {"type": "string"}, "soil": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fertilizer_advice",
            "description": "Fertiliser recommendation for a crop and soil.",
            "parameters": {
                "type": "object",
                "properties": {"crop": {"type": "string"}, "soil": {"type": "string"}},
                "required": ["crop"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rotation_plan",
            "description": "Two-season crop rotation plan after a given crop.",
            "parameters": {
                "type": "object",
                "properties": {"previous_crop": {"type": "string"}},
                "required": ["previous_crop"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Open an app screen with filters pre-filled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "string", "enum": ["market", "predict", "crops", "rotation", "fertilizer", "profile", "home"]},
                    "commodity": {"type": "string"},
                    "district": {"type": "string"},
                },
                "required": ["page"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_external",
            "description": "Open a government/extension page. Only allowlisted hosts are permitted.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]


def allowed_host(url: str) -> bool:
    """True only for https URLs whose host is (or is under) an allowlisted domain."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == d or host.endswith("." + d) for d in settings.open_external_allowlist)


def run_tool(name: str, args: dict, ctx: dict) -> dict:
    """Execute a tool locally. Always returns a JSON-able dict."""
    district = (args.get("district") or ctx.get("district") or "").strip()
    state = (ctx.get("state") or "").strip()

    if name == "get_mandi_prices":
        import mandi_prices

        commodity = (args.get("commodity") or "").strip()
        if not commodity:
            return {"error": "commodity is required"}
        result = mandi_prices.get_price(commodity, district or None, state or None)
        if not result or result.get("price") is None:
            return {
                "commodity": commodity,
                "price": None,
                "available": False,
                "note": "No real mandi record for this commodity in this scope yet.",
            }
        return {
            "commodity": result.get("commodity", commodity),
            "price": result.get("price"),
            "unit": result.get("unit", "₹/quintal"),
            "market": result.get("market"),
            "district": result.get("district"),
            "state": result.get("state"),
            "date": result.get("date"),
            "source": result.get("source"),
            "is_real": bool(result.get("is_real")),
            "min_price": result.get("min_price"),
            "max_price": result.get("max_price"),
            "available": True,
        }

    if name == "get_price_forecast":
        import price_forecast

        commodity = (args.get("commodity") or "").strip()
        if not commodity:
            return {"error": "commodity is required"}
        entries = price_forecast.forecast(
            district=district or None,
            commodity=price_forecast.resolve_name(commodity),
            market=str(args.get("market") or "All"),
        )
        if not entries:
            return {"commodity": commodity, "available": False,
                    "note": "Not enough real mandi history to forecast this commodity yet."}
        e = entries[0]
        return {
            "commodity": e.get("commodity", commodity),
            "current_price": e.get("current_price"),
            "predicted_change_pct": e.get("predicted_change_pct"),
            "mape": e.get("mape"),
            "history_last": e.get("history_last"),
            "history_obs": e.get("history_obs"),
            "trajectory": e.get("trajectory", [])[:14],
            "available": True,
        }

    if name == "recommend_crops":
        import district_data
        from utils.utils import get_default_npk_from_location

        soil = get_default_npk_from_location(
            district=district or None, mode="auto"
        ) or {}
        out = district_data.recommend_for_district(
            float(soil.get("N") or 90), float(soil.get("P") or 40),
            float(soil.get("K") or 40), float(soil.get("ph") or 6.5),
            float(soil.get("temperature") or 27), float(soil.get("humidity") or 65),
            float(soil.get("rainfall") or 100),
            district=district or None, state=state or None,
            season=(args.get("season") or ctx.get("season") or "kharif"),
        )
        if isinstance(out, dict):
            recs = out.get("recommendations") or out.get("results") or out.get("crops") or []
        else:
            recs = out or []
        recs = [r for r in recs if isinstance(r, dict)]
        top = recs[:3]
        return {
            "recommendations": [
                {"crop": r.get("crop"), "score": r.get("display_score") or r.get("confidence")}
                for r in top
            ],
            "available": bool(top),
            "link": "/crops",
        }

    if name == "fertilizer_advice":
        import district_data

        return {"available": False,
                "note": "Fertiliser advice needs the soil card; use the Fertiliser screen.",
                "crop": args.get("crop"),
                "district": district,
                "link": "/fertilizer"}

    if name == "rotation_plan":
        return {"available": False,
                "note": "Rotation plans are computed on the Rotation screen from real soil data.",
                "previous_crop": args.get("previous_crop"),
                "link": "/rotation"}

    if name == "navigate":
        page = (args.get("page") or "home").strip()
        routes = {
            "home": "/home", "market": "/market", "predict": "/predict",
            "crops": "/crops", "rotation": "/rotation",
            "fertilizer": "/fertilizer", "profile": "/profile",
        }
        route = routes.get(page, "/home")
        params = {}
        if args.get("commodity"):
            params["crop"] = args["commodity"]
        if args.get("district"):
            params["district"] = args["district"]
        qs = ("?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())) if params else ""
        return {"action": "navigate", "url": f"{route}{qs}", "page": page}

    if name == "open_external":
        url = (args.get("url") or "").strip()
        if not allowed_host(url):
            return {
                "error": "blocked",
                "note": ("That link is not on the approved government/extension "
                         "list, so I will not open it."),
                "allowlist": settings.open_external_allowlist,
            }
        return {"action": "open_external", "url": url, "needs_confirmation": True}

    return {"error": f"unknown tool {name}"}


# ---------------------------------------------------------------------------
# Deterministic routing (no LLM, no cost)
# ---------------------------------------------------------------------------
PRICE_WORDS = ("price", "rate", "bhav", "bhaav", "भाव", "दर", "କିମ୍ବା", "ભાવ",
               "ಬೆಲೆ", "ధర", "விலை", "വില", "ਕੀਮਤ", "দাম", "भाव")
FORECAST_WORDS = ("forecast", "predict", "tomorrow", "next week", "अनुमान",
                  "भविष्य", "ಮುನ್ಸೂಚನೆ", "అంచనా", "முன்னறிவிப்பு", "പ്രവചനം",
                  "अंदाज", "અનુમાન", "পূর্বাভাস", "ਅੰਦਾਜ਼ਾ", "ପୂର୍ବାନୁମାନ")
SCHEME_WORDS = ("scheme", "yojana", "योजना", "subsidy", "pm kisan", "kcc",
                "ଯୋଜନା", "યોજના", "ಯೋಜನೆ", "పథకం", "திட்டம்", "പദ്ധതി",
                "ਯੋਜਨਾ", "প্রকল্প")

NAV_PAGES = {
    "market": ("market", "mandi", "मंडी", "ಮಾರುಕಟ್ಟೆ", "మార్కెట్", "சந்தை", "മാർക്കറ്റ്", "બજાર", "বাজার", "ਮੰਡੀ", "ବଜାର"),
    "predict": ("forecast page", "predict", "prediction"),
    "rotation": ("rotation", "फसल चक्र", "ಬೆಳೆ ಸರದಿ"),
    "fertilizer": ("fertilizer", "fertiliser", "खाद", "ಗೊಬ್ಬರ"),
    "crops": ("crop recommendation", "which crop", "कौन सी फसल", "ಯಾವ ಬೆಳೆ"),
}

DISTRICT_HINT = re.compile(r"\b(?:in|at|near)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", re.I)


STOPWORDS = {
    "the", "and", "for", "what", "how", "much", "rate", "price", "cost",
    "market", "mandi", "today", "now", "open", "page", "show", "give",
    "tell", "about", "please", "best", "sell", "buy", "crop", "crops",
    "forecast", "predict", "next", "week", "tomorrow", "this", "that",
    "there", "here", "district", "state", "kisan", "scheme", "schemes",
    "current", "latest", "per", "quintal", "kg", "rate", "value", "good",
}


def _known_commodities() -> List[str]:
    try:
        import price_store

        return price_store.distinct_commodities()
    except Exception:  # noqa: BLE001
        return []


def detect_intent(question: str, ctx: dict) -> Optional[dict]:
    """Cheap intent detection so price/forecast/nav never hit the LLM."""
    q = question.lower().strip()
    ctx_crop = (ctx.get("crop") or "").strip()

    # Commodity mentioned in the question? Only accept a token that resolves
    # to a commodity we actually know, so "open market page" never becomes a
    # price question about "Open".
    crop = ctx_crop
    known = {c.lower() for c in _known_commodities()}
    try:
        import mandi_prices

        for token in re.findall(r"[a-zA-Z\u0900-\u0D7F]{3,}", question):
            low = token.lower()
            if low in STOPWORDS:
                continue
            resolved = mandi_prices.resolve_commodity(token)
            if not resolved:
                continue
            if low in known or resolved.lower() in known or (
                resolved.lower() != low and len(low) >= 3
            ):
                crop = resolved
                break
    except Exception:  # noqa: BLE001
        pass

    wants_forecast = any(w in q for w in FORECAST_WORDS)
    wants_price = any(w in q for w in PRICE_WORDS)
    wants_scheme = any(w in q for w in SCHEME_WORDS)

    if wants_scheme:
        return {"kind": "scheme"}

    if wants_price or wants_forecast:
        if not crop:
            return {"kind": "need_crop"}
        return {"kind": "forecast" if wants_forecast else "price", "crop": crop}

    for page, words in NAV_PAGES.items():
        if any(w in q for w in words):
            return {"kind": "navigate", "page": page, "crop": crop or None}

    return None


# ---------------------------------------------------------------------------
# Deterministic answers in the farmer's language
# ---------------------------------------------------------------------------
def _money(v: float) -> str:
    return f"₹{v:,.0f}"


PHRASES = {
    "en": {
        "price": "{crop} in {where} is {price} per quintal at {market} ({date}).",
        "price_none": "I have no real mandi price for {crop} in {where} yet. I will not guess a number.",
        "forecast": "{crop} is {price} today. The 14-day model expects {change} ({mape}% error on backtests).",
        "forecast_none": "There is not enough real mandi history to forecast {crop} yet.",
        "need_crop": "Which crop? For example: “tomato price in Kolar”.",
        "scheme": "Official scheme pages are listed below. I will only open government domains.",
        "nav": "Opening {page} for you.",
        "unsure": "I can answer mandi prices, 14-day forecasts, crop suggestions and open app screens.",
    },
    "hi": {
        "price": "{where} में {crop} का भाव {market} में {price} प्रति क्विंटल है ({date})।",
        "price_none": "{where} में {crop} का असली मंडी भाव अभी उपलब्ध नहीं है। मैं अनुमान नहीं लगाऊँगा।",
        "forecast": "{crop} आज {price} है। 14 दिन का मॉडल {change} का अनुमान देता है ({mape}% त्रुटि)।",
        "forecast_none": "{crop} के लिए अभी पर्याप्त असली मंडी इतिहास नहीं है।",
        "need_crop": "कौन सी फसल? जैसे: “कोलार में टमाटर का भाव”।",
        "scheme": "सरकारी योजना के पेज नीचे हैं। मैं केवल सरकारी वेबसाइट खोलूँगा।",
        "nav": "{page} खोल रहा हूँ।",
        "unsure": "मैं मंडी भाव, 14 दिन का अनुमान, फसल सुझाव और ऐप के पेज बता सकता हूँ।",
    },
    "kn": {
        "price": "{where} ನಲ್ಲಿ {crop} ಬೆಲೆ {market} ನಲ್ಲಿ ಪ್ರತಿ ಕ್ವಿಂಟಾಲ್‌ಗೆ {price} ({date}).",
        "price_none": "{where} ನಲ್ಲಿ {crop} ನಿಜವಾದ ಮಂಡಿ ಬೆಲೆ ಇನ್ನೂ ಇಲ್ಲ. ನಾನು ಊಹಿಸುವುದಿಲ್ಲ.",
        "forecast": "{crop} ಇಂದು {price}. 14 ದಿನದ ಮಾದರಿ {change} ನಿರೀಕ್ಷಿಸುತ್ತದೆ ({mape}% ದೋಷ).",
        "forecast_none": "{crop} ಮುನ್ಸೂಚನೆಗೆ ಸಾಕಷ್ಟು ನಿಜವಾದ ಇತಿಹಾಸ ಇಲ್ಲ.",
        "need_crop": "ಯಾವ ಬೆಳೆ? ಉದಾ: “ಕೋಲಾರದಲ್ಲಿ ಟೊಮೆಟೊ ಬೆಲೆ”.",
        "scheme": "ಸರ್ಕಾರಿ ಯೋಜನೆ ಪುಟಗಳು ಕೆಳಗಿವೆ. ನಾನು ಸರ್ಕಾರಿ ತಾಣಗಳನ್ನಷ್ಟೇ ತೆರೆಯುತ್ತೇನೆ.",
        "nav": "{page} ತೆರೆಯುತ್ತಿದ್ದೇನೆ.",
        "unsure": "ನಾನು ಮಂಡಿ ಬೆಲೆ, 14 ದಿನದ ಮುನ್ಸೂಚನೆ, ಬೆಳೆ ಸಲಹೆ ಮತ್ತು ಪುಟಗಳನ್ನು ತೋರಿಸಬಲ್ಲೆ.",
    },
    "te": {
        "price": "{where} లో {crop} ధర {market} లో క్వింటాల్‌కు {price} ({date}).",
        "price_none": "{where} లో {crop} కు నిజమైన మండి ధర ఇంకా లేదు. నేను ఊహించను.",
        "forecast": "{crop} ఈరోజు {price}. 14 రోజుల మోడల్ {change} అంచనా వేస్తోంది ({mape}% లోపు).",
        "forecast_none": "{crop} అంచనాకు సరిపడా నిజమైన చరిత్ర లేదు.",
        "need_crop": "ఏ పంట? ఉదా: “కోలార్‌లో టొమాటో ధర”.",
        "scheme": "ప్రభుత్వ పథకాల పేజీలు క్రింద ఉన్నాయి. నేను ప్రభుత్వ సైట్లను మాత్రమే తెరుస్తాను.",
        "nav": "{page} తెరుస్తున్నాను.",
        "unsure": "నేను మండి ధరలు, 14 రోజుల అంచనా, పంట సూచనలు చెప్పగలను.",
    },
    "ta": {
        "price": "{where} இல் {crop} விலை {market} இல் குவிண்டாலுக்கு {price} ({date}).",
        "price_none": "{where} இல் {crop} க்கு உண்மையான சந்தை விலை இன்னும் இல்லை. நான் ஊகிக்க மாட்டேன்.",
        "forecast": "{crop} இன்று {price}. 14 நாள் மாதிரி {change} எதிர்பார்க்கிறது ({mape}% பிழை).",
        "forecast_none": "{crop} முன்னறிவிப்புக்கு போதுமான உண்மையான வரலாறு இல்லை.",
        "need_crop": "எந்த பயிர்? எ.கா: “கோலாரில் தக்காளி விலை”.",
        "scheme": "அரசு திட்டப் பக்கங்கள் கீழே உள்ளன. அரசு தளங்களை மட்டுமே திறப்பேன்.",
        "nav": "{page} திறக்கிறேன்.",
        "unsure": "சந்தை விலை, 14 நாள் முன்னறிவிப்பு, பயிர் பரிந்துரைகள் சொல்ல முடியும்.",
    },
    "ml": {
        "price": "{where} ൽ {crop} വില {market} ൽ ക്വിന്റലിന് {price} ({date}).",
        "price_none": "{where} ൽ {crop} ന് യഥാർത്ഥ മണ്ഡി വില ഇല്ല. ഞാൻ ഊഹിക്കില്ല.",
        "forecast": "{crop} ഇന്ന് {price}. 14 ദിവസ മാതൃക {change} പ്രതീക്ഷിക്കുന്നു ({mape}% പിശക്).",
        "forecast_none": "{crop} പ്രവചനത്തിന് മതിയായ യഥാർത്ഥ ചരിത്രമില്ല.",
        "need_crop": "ഏത് വിള? ഉദാ: “കോലാറിൽ തക്കാളി വില”.",
        "scheme": "സർക്കാർ പദ്ധതി പേജുകൾ താഴെയുണ്ട്. സർക്കാർ സൈറ്റുകൾ മാത്രം തുറക്കും.",
        "nav": "{page} തുറക്കുന്നു.",
        "unsure": "മണ്ഡി വില, 14 ദിവസ പ്രവചനം, വിള നിർദ്ദേശങ്ങൾ എനിക്ക് നൽകാം.",
    },
    "mr": {
        "price": "{where} मध्ये {crop} चा दर {market} मध्ये {price} प्रति क्विंटल आहे ({date}).",
        "price_none": "{where} मध्ये {crop} चा खरा बाजारभाव अजून नाही. मी अंदाज लावणार नाही.",
        "forecast": "{crop} आज {price} आहे. 14 दिवसांचा मॉडेल {change} अपेक्षितो ({mape}% त्रुटी).",
        "forecast_none": "{crop} साठी पुरेसा खरा बाजार इतिहास नाही.",
        "need_crop": "कोणते पीक? उदा: “कोलारमध्ये टोमॅटोचा भाव”.",
        "scheme": "सरकारी योजना पाने खाली आहेत. मी फक्त सरकारी संकेतस्थळे उघडेन.",
        "nav": "{page} उघडत आहे.",
        "unsure": "मी बाजारभाव, 14 दिवसांचा अंदाज, पीक सूचना सांगू शकतो.",
    },
    "gu": {
        "price": "{where} માં {crop} નો ભાવ {market} માં {price} પ્રતિ ક્વિન્ટલ છે ({date}).",
        "price_none": "{where} માં {crop} માટે સાચો બજાર ભાવ હજી નથી. હું અંદાજ નહીં લગાવું.",
        "forecast": "{crop} આજે {price} છે. 14 દિવસનું મોડેલ {change} ધારે છે ({mape}% ભૂલ).",
        "forecast_none": "{crop} માટે પૂરતો સાચો ઇતિહાસ નથી.",
        "need_crop": "કયો પાક? દા.ત.: “કોલારમાં ટામેટાનો ભાવ”.",
        "scheme": "સરકારી યોજનાના પાના નીચે છે. હું ફક્ત સરકારી સાઇટ ખોલીશ.",
        "nav": "{page} ખોલી રહ્યો છું.",
        "unsure": "હું બજાર ભાવ, 14 દિવસનું અનુમાન અને પાક સૂચનો આપી શકું.",
    },
    "bn": {
        "price": "{where} এ {crop} এর দাম {market} এ {price} প্রতি কুইন্টাল ({date})।",
        "price_none": "{where} এ {crop} এর সত্যিকারের মণ্ডির দাম এখনও নেই। আমি অনুমান করব না।",
        "forecast": "{crop} আজ {price}। ১৪ দিনের মডেল {change} আশা করছে ({mape}% ত্রুটি)।",
        "forecast_none": "{crop} পূর্বাভাসের জন্য যথেষ্ট সত্যিকারের ইতিহাস নেই।",
        "need_crop": "কোন ফসল? যেমন: “কোলারে টমেটোর দাম”।",
        "scheme": "সরকারি প্রকল্পের পৃষ্ঠা নিচে আছে। আমি শুধু সরকারি সাইট খুলব।",
        "nav": "{page} খুলছি।",
        "unsure": "আমি মণ্ডির দাম, ১৪ দিনের পূর্বাভাস ও ফসলের পরামর্শ দিতে পারি।",
    },
    "pa": {
        "price": "{where} ਵਿੱਚ {crop} ਦਾ ਭਾਅ {market} ਵਿੱਚ {price} ਪ੍ਰਤੀ ਕੁਇੰਟਲ ਹੈ ({date})।",
        "price_none": "{where} ਵਿੱਚ {crop} ਦਾ ਅਸਲੀ ਮੰਡੀ ਭਾਅ ਹਾਲੇ ਨਹੀਂ ਹੈ। ਮੈਂ ਅੰਦਾਜ਼ਾ ਨਹੀਂ ਲਾਵਾਂਗਾ।",
        "forecast": "{crop} ਅੱਜ {price} ਹੈ। 14 ਦਿਨਾਂ ਦਾ ਮਾਡਲ {change} ਦੀ ਉਮੀਦ ਕਰਦਾ ਹੈ ({mape}% ਗਲਤੀ)।",
        "forecast_none": "{crop} ਲਈ ਲੋੜੀਂਦਾ ਅਸਲੀ ਇਤਿਹਾਸ ਨਹੀਂ ਹੈ।",
        "need_crop": "ਕਿਹੜੀ ਫ਼ਸਲ? ਜਿਵੇਂ: “ਕੋਲਾਰ ਵਿੱਚ ਟਮਾਟਰ ਦਾ ਭਾਅ”।",
        "scheme": "ਸਰਕਾਰੀ ਯੋਜਨਾ ਦੇ ਪੰਨੇ ਹੇਠਾਂ ਹਨ। ਮੈਂ ਸਿਰਫ਼ ਸਰਕਾਰੀ ਸਾਈਟ ਖੋਲ੍ਹਾਂਗਾ।",
        "nav": "{page} ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
        "unsure": "ਮੈਂ ਮੰਡੀ ਭਾਅ, 14 ਦਿਨਾਂ ਦਾ ਅੰਦਾਜ਼ਾ ਅਤੇ ਫ਼ਸਲ ਸੁਝਾਅ ਦੱਸ ਸਕਦਾ ਹਾਂ।",
    },
    "or": {
        "price": "{where} ରେ {crop} ଦର {market} ରେ {price} ପ୍ରତି କୁଇଣ୍ଟାଲ ({date})।",
        "price_none": "{where} ରେ {crop} ପାଇଁ ପ୍ରକୃତ ମଣ୍ଡି ଦର ନାହିଁ। ମୁଁ ଅନୁମାନ କରିବି ନାହିଁ।",
        "forecast": "{crop} ଆଜି {price}। ୧୪ ଦିନର ମଡେଲ {change} ଆଶା କରୁଛି ({mape}% ତ୍ରୁଟି)।",
        "forecast_none": "{crop} ପାଇଁ ଯଥେଷ୍ଟ ପ୍ରକୃତ ଇତିହାସ ନାହିଁ।",
        "need_crop": "କେଉଁ ଫସଲ? ଯେପରି: “କୋଲାରରେ ଟମାଟୋ ଦର”।",
        "scheme": "ସରକାରୀ ଯୋଜନା ପୃଷ୍ଠା ତଳେ ଅଛି। ମୁଁ କେବଳ ସରକାରୀ ସାଇଟ ଖୋଲିବି।",
        "nav": "{page} ଖୋଲୁଛି।",
        "unsure": "ମୁଁ ମଣ୍ଡି ଦର, ୧୪ ଦିନର ପୂର୍ବାନୁମାନ ଏବଂ ଫସଲ ପରାମର୍ଶ ଦେଇପାରିବି।",
    },
}

SCHEME_LINKS = [
    ("PM-KISAN", "https://pmkisan.gov.in"),
    ("Soil Health Card", "https://soilhealth.dac.gov.in"),
    ("eNAM mandi", "https://enam.gov.in"),
    ("agmarknet", "https://agmarknet.gov.in"),
    ("myScheme", "https://myscheme.gov.in"),
]


def _phrases(lang: str) -> dict:
    return PHRASES.get(lang) or PHRASES["en"]


def _where(ctx: dict) -> str:
    label = ", ".join(x for x in (ctx.get("district"), ctx.get("state")) if x)
    return label or "All India"


def deterministic_answer(intent: dict, ctx: dict, lang: str) -> dict:
    """Build the reply + cards for a routed intent. No LLM, no cost."""
    p = _phrases(lang)
    where = _where(ctx)

    if intent["kind"] == "need_crop":
        return {"reply": p["need_crop"], "cards": [], "actions": [], "source": "rules"}

    if intent["kind"] == "price":
        result = run_tool("get_mandi_prices", {"commodity": intent["crop"]}, ctx)
        if not result.get("available"):
            return {"reply": p["price_none"].format(crop=intent["crop"], where=where),
                    "cards": [], "actions": [], "source": "rules"}
        return {
            "reply": p["price"].format(
                crop=result["commodity"], where=result.get("district") or where,
                price=_money(result["price"]), market=result.get("market") or "the mandi",
                date=result.get("date") or "",
            ),
            "cards": [{"type": "price", "data": result}],
            "actions": [
                {"type": "navigate", "url": f"/predict?crop={requests.utils.quote(result['commodity'])}",
                 "label": "14-day forecast"},
            ],
            "source": "database",
        }

    if intent["kind"] == "forecast":
        result = run_tool("get_price_forecast", {"commodity": intent["crop"]}, ctx)
        if not result.get("available"):
            return {"reply": p["forecast_none"].format(crop=intent["crop"]),
                    "cards": [], "actions": [], "source": "rules"}
        change = float(result.get("predicted_change_pct") or 0)
        return {
            "reply": p["forecast"].format(
                crop=result["commodity"], price=_money(float(result["current_price"] or 0)),
                change=f"{change:+.1f}%", mape=f"{float(result.get('mape') or 0):.1f}",
            ),
            "cards": [{"type": "forecast", "data": {
                "commodity": result["commodity"],
                "current_price": result["current_price"],
                "predicted_change_pct": change,
                "mape": result.get("mape"),
                "trajectory": result.get("trajectory", []),
            }}],
            "actions": [
                {"type": "navigate", "url": f"/predict?crop={requests.utils.quote(result['commodity'])}",
                 "label": "Open Predict"},
            ],
            "source": "database",
        }

    if intent["kind"] == "navigate":
        result = run_tool("navigate", {"page": intent["page"], "commodity": intent.get("crop")}, ctx)
        return {
            "reply": p["nav"].format(page=intent["page"].capitalize()),
            "cards": [],
            "actions": [{"type": "navigate", "url": result["url"], "label": intent["page"].capitalize(),
                         "auto": True}],
            "source": "rules",
        }

    if intent["kind"] == "scheme":
        links = [{"label": l, "url": u} for l, u in SCHEME_LINKS if allowed_host(u)]
        return {
            "reply": p["scheme"],
            "cards": [],
            "actions": [{"type": "open_external", "url": u["url"], "label": u["label"],
                         "needs_confirmation": True} for u in links],
            "source": "rules",
        }

    return {"reply": p["unsure"], "cards": [], "actions": [], "source": "rules"}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
def build_system_prompt(ctx: dict) -> str:
    """Grounded prompt. Personal data beyond farm context is never injected."""
    today = time.strftime("%d %B %Y")
    lines = [
        "You are AgroSmart AI, a practical farming assistant for Indian farmers.",
        f"Today is {today}.",
        "Reply in the farmer's language, in short simple sentences (max 5 lines).",
        "Use the tools for any price, forecast, crop, fertiliser or rotation "
        "question. Never invent a price or a date. If a tool returns nothing, "
        "say plainly that there is no data yet.",
        "Never mention your model, vendors, or that you are an AI language model.",
    ]
    if ctx.get("name"):
        lines.append(f"The farmer's name is {ctx['name']}.")
    if ctx.get("district") or ctx.get("state"):
        lines.append(f"District: {ctx.get('district') or '-'}, state: {ctx.get('state') or '-'}.")
    if ctx.get("crops"):
        lines.append(f"Crops: {', '.join(ctx['crops'][:6])}.")
    if ctx.get("land_size"):
        lines.append(f"Land: {ctx['land_size']} {ctx.get('land_unit') or 'acres'}.")
    if ctx.get("soil"):
        s = ctx["soil"]
        lines.append(
            "Soil card: N {n}, P {p}, K {k}, pH {ph}, EC {ec}, OC {oc}.".format(
                n=s.get("n"), p=s.get("p"), k=s.get("k"), ph=s.get("ph"),
                ec=s.get("ec"), oc=s.get("oc"),
            )
        )
    lines.append(f"Answer in {ctx.get('lang_name', 'the farmer’s language')}.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def answer(question: str, ctx: dict, history: Optional[List[dict]] = None) -> dict:
    """
    One assistant turn.

    1. cache hit -> return it
    2. deterministic intent -> answer from the database (no LLM)
    3. otherwise -> LLM with tools; honest setup message when no key
    """
    lang = (ctx.get("lang") or "en").lower()
    key = _cache_key(question, lang, ctx.get("district"))
    cached = _cache_get(key)
    if cached is not None:
        return {**cached, "cached": True}

    intent = detect_intent(question, ctx)
    if intent:
        result = deterministic_answer(intent, ctx, lang)
        _cache_put(key, result)
        return {**result, "cached": False}

    if not configured():
        return {
            "reply": SETUP_HINT,
            "cards": [],
            "actions": [],
            "source": "setup",
            "setup_required": ["GEMINI_API_KEY"],
        }

    messages = [{"role": "system", "content": build_system_prompt(ctx)}]
    for m in (history or [])[-settings.chat_max_history_messages:]:
        if m.get("content"):
            messages.append({"role": m.get("role", "user"), "content": str(m["content"])[:2000]})
    messages.append({"role": "user", "content": question[:2000]})

    actions: List[dict] = []
    cards: List[dict] = []
    provider_used = None

    try:
        text, calls, provider_used = call_llm(messages, TOOL_SCHEMAS)
    except RuntimeError as exc:
        logger.warning("all providers failed: %s", exc)
        return {
            "reply": ("The assistant is temporarily unavailable (all free providers "
                      "failed). Price and forecast questions still work — try "
                      "“tomato price in Kolar”."),
            "cards": [],
            "actions": [],
            "source": "error",
        }

    # one round of tool execution, then a final phrasing call
    if calls:
        messages.append({"role": "assistant", "content": text or "", "tool_calls": calls})
        for call in calls[:3]:
            fn = call.get("function", {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_result = run_tool(name, args, ctx)
            if tool_result.get("action"):
                actions.append({**tool_result, "label": tool_result.get("page", "Open")})
            if name in ("get_mandi_prices", "get_price_forecast") and tool_result.get("available"):
                cards.append({
                    "type": "price" if name == "get_mandi_prices" else "forecast",
                    "data": tool_result,
                })
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name or "tool"),
                "name": name,
                "content": json.dumps(tool_result)[:4000],
            })
        try:
            text, _, provider_used = call_llm(messages)
        except RuntimeError:
            pass

    if not text:
        fallback = deterministic_answer({"kind": "unsure"}, ctx, lang)
        text = fallback["reply"]

    result = {
        "reply": text.strip(),
        "cards": cards,
        "actions": actions,
        "source": f"llm:{provider_used}" if provider_used else "llm",
    }
    _cache_put(key, result)
    return {**result, "cached": False}
