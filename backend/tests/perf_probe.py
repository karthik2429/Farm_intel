"""Performance probe: where the milliseconds actually go.

Measures each screen's backing endpoint against a real uvicorn server, and then
re-measures the same calls in-process with outbound HTTP blocked, so the gap
between the two numbers is the cost of external providers (AGMARKNET probe,
Open-Meteo, geocoding) rather than guesswork. Forecast cold-start (model fit +
rolling backtest) and warm-cache calls are reported separately, because the
6-hour cache hides the real cost from a simple benchmark.

Usage (from Farm_intel/backend, server already running):
    ../../collab/venv/bin/python tests/perf_probe.py --base-url http://127.0.0.1:8100

Writes Farm_intel/reports/system-performance.json and prints a markdown table.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

BACKEND = Path(__file__).resolve().parents[1]
REPORTS = BACKEND.parent / "reports"

SCENARIOS: List[Dict[str, Any]] = [
    {"label": "Health check", "method": "GET", "path": "/health"},
    {"label": "Config status", "method": "GET", "path": "/config/status"},
    {"label": "Market: latest price (store hit)", "method": "GET",
     "path": "/market/price", "params": {"commodity": "Banana", "district": "North Goa",
                                          "state": "Goa"}},
    {"label": "Market: price with no data (honest miss)", "method": "GET",
     "path": "/market/price", "params": {"commodity": "Zzzunknown", "district": "Nowhere"}},
    {"label": "Market: history chart", "method": "GET", "path": "/market/history",
     "params": {"commodity": "Banana", "district": "North Goa", "state": "Goa",
                "days": 90}},
    {"label": "Market: scoped crop catalogue", "method": "GET", "path": "/commodities",
     "params": {"district": "North Goa", "state": "Goa"}},
    {"label": "Crop info (agronomy join)", "method": "GET", "path": "/crop/info",
     "params": {"crops": "Rice,Wheat,Tomato,Maize"}},
    {"label": "Crop recommendation (RandomForest)", "method": "POST", "path": "/predict",
     "json": {"district": "North Goa", "state": "Goa", "season": "kharif"}},
    {"label": "Fertilizer recommendation", "method": "POST",
     "path": "/fertilizer/recommend",
     "json": {"crop": "Rice", "soil": "Loamy", "N": 40, "P": 20, "K": 20, "PH": 6.5}},
    {"label": "Rotation suggestions", "method": "POST", "path": "/rotation/suggestions",
     "json": {"prev_crop": "Rice", "N": 90, "P": 40, "K": 40}},
    {"label": "Rotation 2-season plan", "method": "POST", "path": "/rotation/plan",
     "json": {"season1_crop": "Rice", "N": 90, "P": 40, "K": 40,
              "district": "North Goa", "state": "Goa"}},
    {"label": "Forecast 14-day (warm cache)", "method": "POST", "path": "/predict/14day",
     "json": {"district": "North Goa", "state": "Goa", "commodity": "Banana"}},
    {"label": "Forecast single view (weather + factors)", "method": "GET",
     "path": "/predict/single", "params": {"district": "North Goa",
                                            "state": "Goa", "commodity": "Banana"}},
    {"label": "Price factors card", "method": "GET", "path": "/predict/factors",
     "params": {"district": "North Goa", "state": "Goa", "commodity": "Banana"}},
    {"label": "Weather", "method": "GET", "path": "/weather",
     "params": {"district": "North Goa", "state": "Goa"}},
    {"label": "Chat: price question (deterministic)", "method": "POST", "path": "/chat",
     "json": {"messages": [{"role": "user", "content": "Banana price"}],
              "district": "North Goa", "state": "Goa", "lang": "en"}},
    {"label": "Chat: forecast question (deterministic)", "method": "POST", "path": "/chat",
     "json": {"messages": [{"role": "user", "content": "Banana forecast"}],
              "district": "North Goa", "state": "Goa", "lang": "en"}},
]


def _stats(values: List[float]) -> Dict[str, float]:
    values = sorted(values)
    return {
        "runs": len(values),
        "p50_ms": round(statistics.median(values), 1),
        "p95_ms": round(values[max(0, int(len(values) * 0.95) - 1)], 1),
        "max_ms": round(values[-1], 1),
        "mean_ms": round(statistics.fmean(values), 1),
    }


def measure(fn: Callable[[], Any], runs: int) -> Dict[str, float]:
    # The first call is reported separately: it pays for connection setup, lazy
    # imports, geocoding and provider round-trips that the warm p50 hides.
    start = time.perf_counter()
    fn()
    first_ms = round((time.perf_counter() - start) * 1000, 1)
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {**_stats(samples), "first_ms": first_ms}


def http_client(base_url: str):
    import requests

    session = requests.Session()

    def call(scenario: Dict[str, Any]) -> None:
        url = base_url.rstrip("/") + scenario["path"]
        if scenario["method"] == "GET":
            r = session.get(url, params=scenario.get("params"), timeout=90)
        else:
            payload = dict(scenario.get("json") or {})
            if scenario["path"] == "/chat":
                payload["user_id"] = f"perf-{time.perf_counter()}"
            r = session.post(url, json=payload, timeout=90)
        r.raise_for_status()

    return call


class OfflineApp:
    """In-process copy of the app with every outbound HTTP call refused.

    The block stays active for the whole measurement, which is what makes the
    live-vs-offline delta attributable to external providers.
    """

    def __init__(self) -> None:
        import requests

        sys.path.insert(0, str(BACKEND))
        self._requests = requests
        self._original = requests.sessions.Session.request

    def __enter__(self):
        def _blocked(*_a, **_k):
            raise self._requests.exceptions.ConnectionError(
                "perf probe: network blocked")

        self._requests.sessions.Session.request = _blocked
        from fastapi.testclient import TestClient

        import main

        self._client = TestClient(main.app)
        self._client.__enter__()
        return self

    def __exit__(self, *_exc):
        self._client.__exit__(None, None, None)
        self._requests.sessions.Session.request = self._original

    def __call__(self, scenario: Dict[str, Any]) -> None:
        if scenario["method"] == "GET":
            r = self._client.get(scenario["path"], params=scenario.get("params"))
        else:
            payload = dict(scenario.get("json") or {})
            if scenario["path"] == "/chat":
                payload["user_id"] = f"perf-off-{time.perf_counter()}"
            r = self._client.post(scenario["path"], json=payload)
        assert r.status_code < 500, (scenario["label"], r.status_code, r.text[:200])


def forecast_inference(runs: int = 5) -> Dict[str, Any]:
    """Cold forecast cost: model fit + rolling backtest, cache cleared each run."""
    sys.path.insert(0, str(BACKEND))
    import price_forecast
    import price_store

    with price_store._connect() as conn:
        row = conn.execute(
            "SELECT state, district, commodity FROM mandi_prices "
            "GROUP BY state, district, commodity HAVING COUNT(DISTINCT date) >= 60 "
            "ORDER BY COUNT(DISTINCT date) DESC LIMIT 1").fetchone()
    scope = {"state": row["state"], "district": row["district"],
             "commodity": row["commodity"]}

    def cold() -> None:
        price_forecast._cache.clear()
        price_forecast.forecast(district=scope["district"],
                                commodity=scope["commodity"], market="All",
                                state=scope["state"])

    times = []
    for _ in range(runs):
        start = time.perf_counter()
        cold()
        times.append((time.perf_counter() - start) * 1000)

    warm_times = []
    for _ in range(runs):
        start = time.perf_counter()
        price_forecast.forecast(district=scope["district"], commodity=scope["commodity"],
                                market="All", state=scope["state"])
        warm_times.append((time.perf_counter() - start) * 1000)

    def db_only() -> None:
        price_store.history(scope["commodity"], district=scope["district"],
                            state=scope["state"])

    db_times = []
    for _ in range(runs):
        start = time.perf_counter()
        db_only()
        times_ns = (time.perf_counter() - start) * 1000
        db_times.append(times_ns)

    return {
        "scope": scope,
        "forecast_cold": _stats(times),
        "forecast_warm": _stats(warm_times),
        "history_query": _stats(db_times),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://127.0.0.1:8100")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default=str(REPORTS / "system-performance.json"))
    args = ap.parse_args()

    live = http_client(args.base_url)

    results = {"base_url": args.base_url, "runs": args.runs, "endpoints": []}
    # Pass 1: live server (real providers). Must run before the network block.
    for scenario in SCENARIOS:
        results["endpoints"].append({
            "label": scenario["label"],
            "live": measure(lambda s=scenario: live(s), args.runs),
        })

    # Pass 2: same endpoints, in-process, with external HTTP refused.
    with OfflineApp() as offline:
        for row, scenario in zip(results["endpoints"], SCENARIOS):
            row["offline"] = measure(lambda s=scenario: offline(s), args.runs)
            row["external_ms"] = round(
                max(0.0, row["live"]["p50_ms"] - row["offline"]["p50_ms"]), 1)
        results["forecast"] = forecast_inference()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print(f"{'Endpoint':<46}{'first':>8}{'p50':>8}{'p95':>8}{'ext':>8}")
    print("-" * 78)
    for row in results["endpoints"]:
        print(f"{row['label']:<46}{row['live']['first_ms']:>7.0f}ms"
              f"{row['live']['p50_ms']:>7.0f}ms"
              f"{row['live']['p95_ms']:>7.0f}ms{row['external_ms']:>7.0f}ms")
    f = results["forecast"]
    print("-" * 78)
    print(f"{'Forecast cold (fit + backtest)':<46}"
          f"{f['forecast_cold']['p50_ms']:>7.0f}ms{f['forecast_cold']['p95_ms']:>7.0f}ms")
    print(f"{'Forecast warm (cache hit)':<46}"
          f"{f['forecast_warm']['p50_ms']:>7.1f}ms{f['forecast_warm']['p95_ms']:>7.1f}ms")
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
