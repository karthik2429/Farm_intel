"""
AI assistant backend (Phase 3).

Calls an OpenAI-compatible chat completions endpoint server-side. The API
key never reaches the browser. When OPENAI_API_KEY is absent the caller
gets a clear 503 so the UI can show a setup card instead of fake replies.

Config (all optional):
    OPENAI_API_KEY   - the key (Freebuff Developer API or any OpenAI-compatible provider)
    OPENAI_BASE_URL  - default https://freebuff.com/api/v1/paid
    CHAT_MODEL       - default gpt-4o-mini
"""
import os
import time
from typing import Dict, List, Optional

import requests

DEFAULT_BASE_URL = "https://freebuff.com/api/v1/paid"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT_S = 45

# Bounded daily usage per client IP (in-memory, resets on restart).
_DAILY_LIMIT = 50
_usage: Dict[str, Dict] = {}


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def check_rate(ip: str, ip_hash: Optional[str] = None) -> Optional[str]:
    """Return an error message when this client exceeded the daily cap."""
    key = ip_hash or ip
    day = time.strftime("%Y-%m-%d")
    rec = _usage.setdefault(key, {"day": day, "n": 0})
    if rec["day"] != day:
        rec.update({"day": day, "n": 0})
    if rec["n"] >= _DAILY_LIMIT:
        return ("Daily assistant limit reached for today. "
                "Try again tomorrow or check back later.")
    rec["n"] += 1
    return None


def build_system_prompt(location_label: str, weather: Optional[dict] = None) -> str:
    """Grounded system prompt: who the assistant is, where the farmer is,
    and the live conditions. Keeps replies honest about data it lacks."""
    today = time.strftime("%d %B %Y")
    lines = [
        "You are FarmIntel Kisan AI, a practical farming advisor for Indian "
        "farmers. Today is " + today + ".",
        (
            f"The farmer's district context is: {location_label}. "
            if location_label
            else "The farmer's district is unknown."
        ),
    ]
    if weather:
        lines.append(
            f"Live weather there: {weather.get('temperature')}°C, "
            f"{weather.get('humidity')}% humidity, "
            f"{weather.get('rainfall')} mm rain right now."
        )
    lines += [
        "Use short, clear, actionable answers in the language the farmer "
        "writes in. Recommend crops, sowing windows, irrigation, soil/fertilizer "
        "care, pest management and market timing.",
        "The app already serves real mandi prices, crop recommendations, "
        "fertilizer and rotation advice; refer the farmer to those screens "
        "when that is the better tool.",
        "Never invent prices, dates or chemical dosages. If unsure, say so "
        "and suggest the local Krishi Vigyan Kendra or agriculture officer.",
    ]
    return "\n".join(lines)


def chat(turns: List[dict], system_prompt: str,
         max_turns: int = 12) -> str:
    """One round-trip to the chat completions API. Raises on failure."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    base = (os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
    model = (os.environ.get("CHAT_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL).strip()
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt},
                     *turns[-max_turns:]],
        "temperature": 0.4,
        "max_tokens": 700,
    }
    res = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        json=body,
        timeout=TIMEOUT_S,
    )
    if res.status_code != 200:
        detail = (res.text or "").strip()[:300]
        raise RuntimeError(f"LLM API {res.status_code}: {detail}")
    data = res.json()
    reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not reply:
        raise RuntimeError("LLM API returned an empty reply")
    return reply
