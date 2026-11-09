"""Shared harness for the system-level suite.

Two rules keep this suite meaningful and cheap:

1. **No surprise internet.** Every test runs with outbound HTTP blocked by
   default, so a passing suite means the API degrades honestly instead of
   depending on a provider being up. Tests that really need the network opt in
   with ``@pytest.mark.live`` (they are skipped when ``--live`` isn't passed).
2. **Real data, discovered not hardcoded.** Fixtures pick the strongest
   district/state/commodity the local store actually has, so the suite keeps
   testing the pipeline as the ingest data changes instead of asserting on a
   row that was deleted a month ago.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import requests

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False,
                     help="allow real outbound HTTP for @pytest.mark.live tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs real network access")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs network; run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Outbound HTTP block (default) + recording, so failures can name the call
# ---------------------------------------------------------------------------
class NetworkBlocked(requests.exceptions.ConnectionError):
    """Raised instead of touching the internet in an offline test."""


@pytest.fixture(autouse=True)
def external_http(monkeypatch, request) -> List[str]:
    """Block outbound HTTP unless the test is marked ``live``.

    Returns a list that collects attempted URLs, which lets a test assert that
    e.g. /weather *tried* the provider and fell back, rather than silently
    never calling it.
    """
    calls: List[str] = []
    if request.node.get_closest_marker("live"):
        return calls

    def _blocked(session, method, url, *args, **kwargs):
        calls.append(f"{method} {url}")
        raise NetworkBlocked(f"outbound HTTP blocked in tests: {method} {url}")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
    return calls


@pytest.fixture(autouse=True)
def reset_runtime_state():
    """Clear in-memory caches and rate-limit buckets between tests.

    Without this a 429 from one test leaks into the next, and a cached forecast
    hides a broken code path.
    """
    import chat
    import price_forecast

    from utils import utils as utils_module

    chat._buckets.clear()
    chat._global_bucket.clear()
    chat._cache.clear()
    chat._model_cooldown.clear()
    price_forecast._cache.clear()
    utils_module._WEATHER_CACHE.clear()
    utils_module._WEATHER_FC_CACHE.clear()
    yield


@pytest.fixture(scope="session")
def api():
    """The FastAPI module (imported once; the models load at startup)."""
    import main

    return main


@pytest.fixture()
def client(api):
    """TestClient with startup/shutdown events, i.e. models actually loaded."""
    from fastapi.testclient import TestClient

    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def chat_module():
    import chat

    return chat


@pytest.fixture()
def store():
    import price_store

    return price_store


# ---------------------------------------------------------------------------
# Data facts discovered from the real price store
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def facts() -> Dict[str, Any]:
    """Pick scopes the store genuinely covers, so tests exercise real paths."""
    import datetime as dt

    import price_store

    out: Dict[str, Any] = {}
    fresh_cutoff = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    with price_store._connect() as conn:
        # A pair that a "/latest price" request must answer *today*.
        fresh = conn.execute(
            """
            SELECT state, district, commodity, MAX(date) AS last
            FROM mandi_prices
            WHERE district = trim(district) AND state = trim(state)
            GROUP BY state, district, commodity
            HAVING last >= ?
            ORDER BY last DESC
            LIMIT 1
            """,
            (fresh_cutoff,),
        ).fetchone()
        if fresh:
            out.update({
                "fresh_state": fresh["state"],
                "fresh_district": fresh["district"],
                "fresh_commodity": fresh["commodity"],
                "fresh_date": fresh["last"],
            })

        daily = conn.execute(
            """
            SELECT state, district, commodity, COUNT(DISTINCT date) AS days
            FROM mandi_prices
            GROUP BY state, district, commodity
            HAVING days >= 60
            ORDER BY days DESC LIMIT 1
            """
        ).fetchone()
        if daily:
            out.update({
                "daily_state": daily["state"],
                "daily_district": daily["district"],
                "daily_commodity": daily["commodity"],
                "daily_days": int(daily["days"]),
            })

        monthly = conn.execute(
            """
            SELECT state, commodity, COUNT(DISTINCT year * 100 + month) AS months
            FROM mandi_monthly
            GROUP BY state, commodity
            HAVING months >= 12
            ORDER BY months DESC LIMIT 1
            """
        ).fetchone()
        if monthly:
            out.update({
                "monthly_state": monthly["state"],
                "monthly_commodity": monthly["commodity"],
                "monthly_months": int(monthly["months"]),
            })

    if not out.get("fresh_district") and "daily_district" not in out and "monthly_state" not in out:
        pytest.skip("price store is empty — run the daily ingest first")
    return out


@pytest.fixture()
def forecast_scope(facts) -> Dict[str, Optional[str]]:
    """A scope where a 14-day forecast is genuinely possible."""
    if "daily_district" in facts:
        return {"district": facts["daily_district"], "state": facts["daily_state"],
                "commodity": facts["daily_commodity"]}
    pytest.skip("no scope with enough daily history for a forecast")


@pytest.fixture()
def price_scope(facts) -> Dict[str, str]:
    """A scope whose latest price is fresh enough to be served as "today"."""
    if "fresh_district" not in facts:
        pytest.skip("no market pair fresh within 45 days")
    return {"district": facts["fresh_district"], "state": facts["fresh_state"],
            "commodity": facts["fresh_commodity"]}


def price_in_reply(reply: str) -> Optional[float]:
    """Pull the first ₹ amount out of an assistant sentence."""
    import re

    m = re.search(r"₹\s*([0-9][0-9,]*\.?[0-9]*)", reply or "")
    return float(m.group(1).replace(",", "")) if m else None
