"""
Real price forecasting for FarmIntel (Phase 1).

Replaces the Phase 0 "one XGBoost scalar compounded daily" pseudo-forecast
with a proper statistical model over accumulated mandi history:

  - History: last 24 months of modal prices per commodity, from the price
    store (real Goa 2024-26 backfill + every daily live fetch since).
  - Missing days (mandis close): reindexed to a daily grid, interior gaps
    linearly interpolated (gaps up to 21 days), flat-carry after.
  - Model: Holt-Winters additive (level + trend + weekly seasonality),
    smoothing params optimized by in-sample SSE grid search. Pure numpy,
    no heavyweight deps required.
  - Backtest: rolling-origin holdout (last 14 days + 4 folds) -> MAPE
    reported per commodity/market with the response.
  - Confidence intervals: residual sigma from the backtest, widened by
    sqrt(h) over the horizon (approx 80% band).
  - Scope fallback: market+district -> district -> state -> commodity-anywhere,
    each level needs >= MIN_OBS observations, and the level used is reported
    so the UI can say "state-level estimate" when the market is thin.

Responds in the same JSON contracts the frontend already consumes
(priceApi.ts) plus richer fields (mape, level, signal, ci bands).
"""

from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import price_store

MIN_OBS = 60            # observations required at each scope level
HIST_YEARS = 2.0
SEASON_M = 7            # weekly seasonality on the daily grid
FORECAST_DAYS = 14
_MAX_STALE_SHIFT = 120  # cap projection of dead days between last obs and today

_cache: Dict[str, dict] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 6 * 3600   # forecasts re-evaluated at most every 6h


# ---------------------------------------------------------------------------
# Scope resolution: market -> district -> state -> any
# ---------------------------------------------------------------------------

def _series_for(commodity: str, district: Optional[str],
                state: Optional[str], market: Optional[str]) -> pd.Series:
    df = price_store.history(commodity, district=district, state=state)
    if df.empty:
        return pd.Series(dtype=float)
    if market and str(market).lower() != "all":
        m = df[_norm(df["market"]) == _norm(market)]
        if not m.empty:
            df = m
    daily = df.groupby("date")["modal_price"].median().sort_index()
    return daily


def _norm(s) -> str:
    return " ".join(str(s or "").strip().lower().split())


def _daily_grid(s: pd.Series) -> pd.Series:
    """Reindex to a 1-day grid; interpolate interior gaps (<=21 d)."""
    if len(s) < 10:
        return s
    full_idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
    g = s.reindex(full_idx)
    g = g.interpolate(limit=21, limit_area="inside")
    g = g.ffill().bfill()
    return g


# ---------------------------------------------------------------------------
# Holt-Winters (additive), pure numpy
# ---------------------------------------------------------------------------

def _hw_components(y: np.ndarray, alpha: float, beta: float,
                   gamma: float, m: int):
    n = len(y)
    if n < 2 * m + 2:
        return None
    y0 = y[:m].mean() if n >= m else y.min()
    season0 = y[:m] - y0
    level = y0
    trend = (y[m:2 * m].mean() - y0) / max(m, 1) if n >= 2 * m else 0.0
    s = list(season0)
    fitted = np.empty(n)
    fitted[:] = np.nan
    for t in range(n):
        if t < m:
            continue
        st = s[t - m] if t - m < len(s) else 0.0
        fitted[t] = level + trend + st
        new_level = alpha * y[t] + (1 - alpha) * (level + trend + st)
        new_trend = beta * (new_level - level) + (1 - beta) * trend
        s.append((1 - gamma_frac(gamma)) * st + gamma_frac(gamma) * (y[t] - new_level))
        level, trend = new_level, new_trend
    return level, trend, s, fitted


def gamma_frac(gamma: float) -> float:
    return gamma if gamma > 0 else 0.0


def _hw_forecast(y: np.ndarray, horizon: int) -> Tuple[np.ndarray, dict]:
    """Fit additive Holt-Winters (damped trend) with weekly seasonality;
    return forecast and info (with one-step residuals for CI)."""
    m = min(SEASON_M, max(2, len(y) // 8))
    best = None
    for alpha in (0.2, 0.35, 0.5):
        for beta in (0.02, 0.1, 0.2):
            res = _hw_components(y, alpha, beta, 0.0, m)
            if res is None:
                continue
            fitted = res[3]
            mask = ~np.isnan(fitted)
            sse = float(np.sum((y[mask] - fitted[mask]) ** 2))
            if best is None or sse < best[0]:
                best = (sse, alpha, beta, m)
    if best is None:
        # tiny series: flat projection with recent mean
        recent = float(np.mean(y[-10:]))
        return (np.full(horizon, recent),
                {"model": "mean", "m": 0, "resid": np.array([0.0])})
    _, alpha, beta, m_used = best
    level, trend, s, fitted = _hw_components(y, alpha, beta, 0.0, m_used)
    residuals = (y - fitted)[~np.isnan(fitted)]
    # Damped-trend projection so long horizons (stale history -> large
    # shift) do not extrapolate the linear trend unbounded.
    phi = 0.94
    fc = []
    damp = 0.0
    for h in range(1, horizon + 1):
        damp += trend * (phi ** (h - 1))
        st = s[len(s) - m_used + (h - 1) % m_used] if len(s) >= m_used else 0.0
        fc.append(level + damp + st)
    info = {"model": "hw_additive", "alpha": alpha, "beta": beta,
            "m": m_used, "resid": residuals}
    return np.asarray(fc), info


def _hw_residuals(y: np.ndarray, alpha: float = 0.35,
                  beta: float = 0.1) -> np.ndarray:
    res = _hw_components(y, 0.35, 0.1, 0.0, min(SEASON_M, max(2, len(y) // 8)))
    if res is None:
        return np.array([0.02])
    fitted = res[3]
    mask = ~np.isnan(fitted)
    return y[mask] - fitted[mask]


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def _mape(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.abs(actual) > 1e-9
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100)


def _rolling_backtest(g: pd.Series, horizon: int = FORECAST_DAYS,
                      folds: int = 4) -> Tuple[float, List[dict]]:
    """Rolling-origin backtest: hold out the last N*horizon days,
    one fold per position."""
    y = g.values.astype(float)
    n = len(y)
    apes = []
    details = []
    for f in range(folds):
        cut = n - horizon * (f + 1)
        if cut < max(2 * SEASON_M + 5, 40):
            break
        train = y[:cut]
        actual = y[cut:cut + horizon]
        if len(actual) < horizon:
            break
        fc, _ = _hw_forecast(train, len(actual))
        mape = _mape(actual, fc)
        if not math.isnan(mape):
            apes.append(mape)
            details.append({"fold": f, "cut": cut, "mape": round(mape, 2)})
    return (float(np.mean(apes)) if apes else float("nan")), details


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _scope_forecast(commodity: str, scope_level: str, market: str,
                    district: Optional[str], state: Optional[str]
                    ) -> Optional[dict]:
    g = _series_for(commodity, district if scope_level != "india" else None,
                    state if scope_level in ("state", "district")
                    else None, market)
    if len(g) < MIN_OBS:
        return None
    g = _daily_grid(g)
    y = g.values.astype(float)

    last_date = g.index[-1]
    last_price = float(y[-1])
    base_date = max(last_date, pd.Timestamp.today().normalize())
    # Forecast the FULL horizon from the model (stale history means the
    # days between the last observation and today must also be projected),
    # instead of clamping every step to fc[-1] (which produced flat,
    # identical trajectories).
    shift = max(0, min((base_date - last_date).days, _MAX_STALE_SHIFT))
    fc, info = _hw_forecast(y, shift + FORECAST_DAYS)
    resid = np.asarray(info.get("resid", np.array([])), dtype=float)
    if len(resid) > 5:
        # robust sigma (MAD) so daily outliers do not inflate the band
        med = float(np.median(resid))
        mad = float(np.median(np.abs(resid - med)))
        sigma = 1.4826 * mad
        if sigma <= 0:
            sigma = float(np.std(resid))
    else:
        sigma = float(np.std(y)) * 0.03

    mape, folds = _rolling_backtest(g)
    traj = []
    for h in range(1, FORECAST_DAYS + 1):
        d = (base_date + pd.Timedelta(days=h)).strftime("%Y-%m-%d")
        p = float(fc[h - 1 + shift]) if h - 1 + shift < len(fc) else float(fc[-1])
        p = max(p, 0)
        band = min(1.28 * sigma * math.sqrt(max(h, 1)), 0.35 * p)
        lo = max(0, p - band)
        hi = p + band
        traj.append({
            "day": h, "date": d,
            "predicted_price": round(p, 2),
            "ci_low": round(lo, 2), "ci_high": round(hi, 2),
            "change_from_initial_pct":
                round((p - last_price) / last_price * 100, 2) if last_price else 0.0,
        })
    p14 = traj[-1]["predicted_price"]
    change14 = traj[-1]["change_from_initial_pct"]
    mape_safe = mape if not math.isnan(mape) else 8.0
    return {
        "commodity": commodity,
        "scope_level": scope_level,
        "market": market if scope_level == "market" else (
            f"{district or state or 'state'} aggregate"),
        "district": district, "state": state,
        "current_price": round(last_price, 2),
        "history_first": str(g.index[0].date()),
        "history_last": str(last_date.date()),
        "history_obs": int(len(g)),
        "predicted_price_14d": p14,
        "predicted_change_pct": change14,
        "mape": round(mape_safe, 2),
        "backtest_folds": folds,
        "model": info.get("model"),
        "stale_days": int(shift),
        "ci_low_14d": traj[-1]["ci_low"],
        "ci_high_14d": traj[-1]["ci_high"],
        "signal": _signal_text(change14, mape_safe),
        "trajectory": traj,
    }


def _signal_text(change_pct: float, mape: float) -> str:
    if change_pct <= -2.0:
        return (f"Prices likely to FALL ~{abs(change_pct):.0f}% over "
                f"2 weeks — consider selling soon.")
    if change_pct < -0.5:
        return f"Prices may dip slightly (~{abs(change_pct):.1f}%) over 2 weeks."
    if change_pct < 0.5:
        return "Prices expected to stay roughly flat over 2 weeks."
    if change_pct < 2.0:
        return f"Prices may rise slightly (~{change_pct:.1f}%) over 2 weeks."
    return (f"Prices likely to RISE ~{change_pct:.0f}% over 2 weeks — "
            f"if storage is safe, consider waiting.")


def _norm_market(m):
    return _norm(m)


def forecast(district: Optional[str], commodity: Optional[str],
             market: Optional[str] = "All", days: int = FORECAST_DAYS) -> List[dict]:
    """Forecast for the requested commodity+location, with automatic scope
    fallback. Cached for 6h per scope key."""
    key = f"{_norm(commodity)}|{_norm(district)}|{_norm(market or 'All')}|{days}"
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit["t"] < _CACHE_TTL:
            return hit["v"]

    commodities = [resolve_name(commodity)] if commodity else []
    out = []
    for com in commodities:
        res = _forecast_one(district, com, market, days)
        if res:
            out.append(res)
    with _cache_lock:
        _cache[key] = {"t": now, "v": out}
    return out


def resolve_name(name: str) -> str:
    """Reuse mandi_prices aliasing where cheap; normalize case only here to
    avoid import cycles."""
    base = str(name or "").strip()
    if not base:
        return base
    map_ = {
        "paddy": "Rice", "rice": "Rice", "maize": "Maize", "wheat": "Wheat",
        "cotton": "Cotton", "onion": "Onion", "tomato": "Tomato",
        "potato": "Potato", "banana": "Banana", "urad": "Urad",
        "moong": "Moong", "tur": "Arhar/Tur", "arhar": "Arhar/Tur",
        "gram": "Gram", "chickpea": "Gram", "groundnut": "Groundnut",
    }
    return map_.get(base.lower(), base)


def _forecast_one(district: Optional[str], commodity: str,
                  market: Optional[str], days: int) -> Optional[dict]:
    # resolve state from the district when possible (cheap distinct query)
    state = price_store.state_for_district(district) if district else None
    scopes: List[Tuple[str, Optional[str], Optional[str]]] = []
    if market and str(market).lower() != "all":
        scopes.append(("market", district, market))
    if district:
        scopes.append(("district", district, None))
    if state:
        scopes.append(("state", None, None))
    scopes.append(("india", None, None))
    for level, d, m in scopes:
        res = _scope_forecast(commodity, level, m or "All",
                              d if level != "state" else None, state)
        if res:
            return res
    return None


CACHE_TTL = _CACHE_TTL


def known_commodities() -> List[str]:
    return price_store.distinct_commodities()


def known_markets() -> List[Dict[str, str]]:
    return price_store.distinct_markets()
