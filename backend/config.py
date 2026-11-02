"""
Single typed configuration module for the FarmIntel backend (Phase 0).

Every environment read in the backend goes through here. No other module
should call ``os.environ`` for app configuration, and no key is ever
hardcoded. Values are optional: a missing key disables its feature, it never
crashes the app.

    from config import settings
    settings.data_gov_api_key
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR.parent / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Load KEY=VALUE lines into os.environ without overriding real env vars."""
    if not path.exists():
        return
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


load_env_file()


def _s(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _i(name: str, default: int) -> int:
    try:
        return int(float(_s(name, str(default))))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = False) -> bool:
    raw = _s(name, "").lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _l(name: str, default: str = "") -> List[str]:
    raw = _s(name, default)
    return [p.strip() for p in raw.split(",") if p.strip()]


class Settings:
    """Typed, lazily-read application settings."""

    # runtime
    @property
    def backend_port(self) -> int:
        return _i("BACKEND_PORT", 8000)

    @property
    def cors_origins(self) -> List[str]:
        raw = _l("CORS_ORIGINS", "*")
        return raw or ["*"]

    @property
    def app_env(self) -> str:
        return _s("APP_ENV", "development").lower()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # mandi pipeline
    @property
    def data_gov_api_key(self) -> str:
        return _s("DATA_GOV_API_KEY")

    @property
    def data_gov_resource_id(self) -> str:
        return _s("DATA_GOV_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070")

    @property
    def mandi_db_path(self) -> str:
        return _s("MANDI_DB_PATH", str(BASE_DIR / "mandi_price_store.db"))

    @property
    def mandi_cache_ttl_minutes(self) -> int:
        return _i("MANDI_CACHE_TTL_MINUTES", 180)

    # supabase (server side)
    @property
    def supabase_url(self) -> str:
        return _s("SUPABASE_URL")

    @property
    def supabase_anon_key(self) -> str:
        return _s("SUPABASE_ANON_KEY")

    @property
    def supabase_service_key(self) -> str:
        return _s("SUPABASE_SERVICE_KEY")

    # LLM chain
    @property
    def gemini_api_key(self) -> str:
        return _s("GEMINI_API_KEY")

    @property
    def gemini_model(self) -> str:
        return _s("GEMINI_MODEL", "gemini-2.0-flash")

    @property
    def groq_api_key(self) -> str:
        return _s("GROQ_API_KEY")

    @property
    def groq_model(self) -> str:
        return _s("GROQ_MODEL", "llama-3.3-70b-versatile")

    @property
    def openrouter_api_key(self) -> str:
        return _s("OPENROUTER_API_KEY")

    @property
    def openrouter_model(self) -> str:
        return _s("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

    @property
    def ollama_base_url(self) -> str:
        return _s("OLLAMA_BASE_URL")

    @property
    def ollama_model(self) -> str:
        return _s("OLLAMA_MODEL", "llama3.1")

    # chat limits
    @property
    def chat_max_output_tokens(self) -> int:
        return _i("CHAT_MAX_OUTPUT_TOKENS", 700)

    @property
    def chat_max_history_messages(self) -> int:
        return _i("CHAT_MAX_HISTORY_MESSAGES", 6)

    @property
    def chat_rate_limit_per_user_per_hour(self) -> int:
        return _i("CHAT_RATE_LIMIT_PER_USER_PER_HOUR", 40)

    @property
    def chat_cache_ttl_hours(self) -> int:
        return _i("CHAT_CACHE_TTL_HOURS", 6)

    # speech
    @property
    def speech_provider(self) -> str:
        return _s("SPEECH_PROVIDER", "browser").lower()

    @property
    def bhashini_user_id(self) -> str:
        return _s("BHASHINI_USER_ID")

    @property
    def bhashini_ulca_api_key(self) -> str:
        return _s("BHASHINI_ULCA_API_KEY")

    @property
    def bhashini_inference_api_key(self) -> str:
        return _s("BHASHINI_INFERENCE_API_KEY")

    @property
    def sarvam_api_key(self) -> str:
        return _s("SARVAM_API_KEY")

    # external services
    @property
    def open_meteo_base_url(self) -> str:
        return _s("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1").rstrip("/")

    @property
    def nominatim_user_agent(self) -> str:
        return _s("NOMINATIM_USER_AGENT", "farmintel/3.0 (+https://farmintel.local)")

    @property
    def nominatim_base_url(self) -> str:
        return _s("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")

    @property
    def soilgrids_base_url(self) -> str:
        return _s("SOILGRIDS_BASE_URL", "https://rest.isric.org/soilgrids/v2.0").rstrip("/")

    @property
    def nasa_power_base_url(self) -> str:
        return _s(
            "NASA_POWER_BASE_URL",
            "https://power.larc.nasa.gov/api/temporal/daily/point",
        ).rstrip("/")

    @property
    def geo_service_account(self) -> str:
        return _s("GEE_SERVICE_ACCOUNT")

    @property
    def gee_private_key_path(self) -> str:
        return _s("GEE_PRIVATE_KEY_PATH")

    @property
    def copernicus_client_id(self) -> str:
        return _s("COPERNICUS_CLIENT_ID")

    @property
    def copernicus_client_secret(self) -> str:
        return _s("COPERNICUS_CLIENT_SECRET")

    @property
    def unsplash_access_key(self) -> str:
        return _s("UNSPLASH_ACCESS_KEY")

    @property
    def pexels_api_key(self) -> str:
        return _s("PEXELS_API_KEY")

    # internal tuning knobs (not secrets, documented for completeness)
    @property
    def ingest_max_rows(self) -> int:
        return _i("FARMINTEL_INGEST_MAX_ROWS", 200000)

    @property
    def data_dir(self) -> str:
        return _s("FARMINTEL_DATA_DIR", ".")

    @property
    def price_db_override(self) -> str:
        return _s("FARMINTEL_PRICE_DB")

    @property
    def open_external_allowlist(self) -> List[str]:
        return [
            h.lower()
            for h in _l(
                "OPEN_EXTERNAL_ALLOWLIST",
                "agmarknet.gov.in,enam.gov.in,pmkisan.gov.in,"
                "soilhealth.dac.gov.in,mausam.imd.gov.in,myscheme.gov.in,kisan.gov.in",
            )
        ]


settings = Settings()


# Signup links shown next to each missing key in the dev setup panel.
SIGNUP_LINKS: Dict[str, str] = {
    "DATA_GOV_API_KEY": "https://data.gov.in/user/register",
    "SUPABASE_URL": "https://supabase.com/dashboard",
    "SUPABASE_ANON_KEY": "https://supabase.com/dashboard/project/_/settings/api",
    "SUPABASE_SERVICE_KEY": "https://supabase.com/dashboard/project/_/settings/api",
    "GEMINI_API_KEY": "https://aistudio.google.com/apikey",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "OPENROUTER_API_KEY": "https://openrouter.ai/keys",
    "OLLAMA_BASE_URL": "https://ollama.com/download",
    "BHASHINI_USER_ID": "https://bhashini.gov.in",
    "BHASHINI_ULCA_API_KEY": "https://bhashini.gov.in",
    "BHASHINI_INFERENCE_API_KEY": "https://bhashini.gov.in",
    "SARVAM_API_KEY": "https://dashboard.sarvam.ai",
    "UNSPLASH_ACCESS_KEY": "https://unsplash.com/developers",
    "PEXELS_API_KEY": "https://www.pexels.com/api/",
    "COPERNICUS_CLIENT_ID": "https://dataspace.copernicus.eu",
    "GEE_SERVICE_ACCOUNT": "https://earthengine.google.com",
}


def _bool(value: object) -> bool:
    return bool(str(value or "").strip())


def service_status() -> Dict[str, object]:
    """Booleans only — never a key value. Safe to expose."""
    llm = {
        "gemini": _bool(settings.gemini_api_key),
        "groq": _bool(settings.groq_api_key),
        "openrouter": _bool(settings.openrouter_api_key),
        "ollama": _bool(settings.ollama_base_url),
    }
    configured = {
        "mandi_live": _bool(settings.data_gov_api_key),
        "supabase": _bool(settings.supabase_url) and _bool(settings.supabase_anon_key),
        "supabase_service": _bool(settings.supabase_service_key),
        "chat_llm": any(llm.values()),
        "speech_bhashini": _bool(settings.bhashini_user_id)
        and _bool(settings.bhashini_ulca_api_key),
        "speech_sarvam": _bool(settings.sarvam_api_key),
        "satellite_gee": _bool(settings.geo_service_account),
        "crop_photos_unsplash": _bool(settings.unsplash_access_key),
        "crop_photos_pexels": _bool(settings.pexels_api_key),
    }
    missing = [
        {"var": name, "signup": link}
        for name, link in SIGNUP_LINKS.items()
        if not _VAR_VALUE[name]()
    ]
    return {
        "env": settings.app_env,
        "configured": configured,
        "llm_providers": llm,
        "speech_provider": settings.speech_provider,
        "external_allowlist": settings.open_external_allowlist,
        "missing": missing,
    }


_VAR_VALUE = {
    "DATA_GOV_API_KEY": lambda: settings.data_gov_api_key,
    "SUPABASE_URL": lambda: settings.supabase_url,
    "SUPABASE_ANON_KEY": lambda: settings.supabase_anon_key,
    "SUPABASE_SERVICE_KEY": lambda: settings.supabase_service_key,
    "GEMINI_API_KEY": lambda: settings.gemini_api_key,
    "GROQ_API_KEY": lambda: settings.groq_api_key,
    "OPENROUTER_API_KEY": lambda: settings.openrouter_api_key,
    "OLLAMA_BASE_URL": lambda: settings.ollama_base_url,
    "BHASHINI_USER_ID": lambda: settings.bhashini_user_id,
    "BHASHINI_ULCA_API_KEY": lambda: settings.bhashini_ulca_api_key,
    "BHASHINI_INFERENCE_API_KEY": lambda: settings.bhashini_inference_api_key,
    "SARVAM_API_KEY": lambda: settings.sarvam_api_key,
    "UNSPLASH_ACCESS_KEY": lambda: settings.unsplash_access_key,
    "PEXELS_API_KEY": lambda: settings.pexels_api_key,
    "COPERNICUS_CLIENT_ID": lambda: settings.copernicus_client_id,
    "GEE_SERVICE_ACCOUNT": lambda: settings.geo_service_account,
}
