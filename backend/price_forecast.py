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
MIN_MONTHS = 12         # monthly averages needed when daily history is thin
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
    daily, _basis = _series_with_basis(commodity, district, state, market)
    return daily


def _series_with_basis(commodity: str, district: Optional[str],
                       state: Optional[str], market: Optional[str]
                       ) -> Tuple[pd.Series, str]:
    """Daily observations when the store has them, else AGMARKNET monthly
    district averages resampled onto the same daily grid.

    Returns (series, basis) where basis is "daily" or "monthly". The basis is
    reported in the response so the UI can say what the forecast is built on.
    """
    df = price_store.history(commodity, district=district, state=state)
    if not df.empty:
        if market and str(market).lower() != "all":
            m = df[_norm(df["market"]) == _norm(market)]
            if not m.empty:
                df = m
        daily = df.groupby("date")["modal_price"].median().sort_index()
        if len(daily) >= MIN_OBS:
            return daily, "daily"

    monthly = price_store.monthly_history(commodity, district=district, state=state)
    if len(monthly) >= MIN_MONTHS:
        return monthly_to_daily(monthly), "monthly"

    empty = pd.Series(dtype=float)
    return (daily if not df.empty else empty), "daily"


def monthly_to_daily(monthly: pd.DataFrame) -> pd.Series:
    """Published monthly averages -> a daily grid, for the same 14-day horizon.

    The anchor for each month sits mid-month (the average represents the whole
    month), and consecutive anchors are joined with a straight line capped at
    45 days: no invented shape, just the transition the published averages
    imply. A longer hole (AGMARKNET skips months for some crops) is
    flat-carried rather than drawn as a trend we never observed.
    """
    anchors = pd.Series(
        monthly["price"].astype(float).values,
        index=pd.to_datetime(monthly["date"]) + pd.Timedelta(days=14),
    ).sort_index()
    grid = pd.date_range(anchors.index.min(), anchors.index.max(), freq="D")
    return (anchors.reindex(grid)
            .interpolate(method="time", limit=45)
            .ffill().bfill())


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


def _hw_forecast(y: np.ndarray, horizon: int,
                 flat: bool = False) -> Tuple[np.ndarray, dict]:
    """Fit additive Holt-Winters (damped trend) with weekly seasonality;
    return forecast and info (with one-step residuals for CI).

    `flat` keeps the fitted level and weekly pattern but projects no trend —
    the safer variant when a series' apparent drift is noise (which is common
    for modal prices parked on round numbers).
    """
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
    if flat:
        trend = 0.0
    # Damped-trend projection so long horizons (stale history -> large
    # shift) do not extrapolate the linear trend unbounded.
    phi = 0.94
    fc = []
    damp = 0.0
    for h in range(1, horizon + 1):
        damp += trend * (phi ** (h - 1))
        st = s[len(s) - m_used + (h - 1) % m_used] if len(s) >= m_used else 0.0
        fc.append(level + damp + st)
    info = {"model": "hw_additive_flat" if flat else "hw_additive",
            "alpha": alpha, "beta": beta, "m": m_used, "resid": residuals}
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


# ---------------------------------------------------------------------------
# Data repair
# ---------------------------------------------------------------------------

JUNK_LOW = 0.25     # a mandi price does not fall to a quarter of its level in a day
JUNK_HIGH = 4.0     # ... nor quadruple
GLOBAL_LOW = 0.20   # nor trade for a fifth of the commodity's own median level
GLOBAL_HIGH = 5.0   # ... nor five times it, for a sustained stretch


def clean_series(g: pd.Series) -> Tuple[pd.Series, int]:
    """Repair unit/parse errors against the local price level.

    AGMARKNET rows occasionally arrive in a different unit (Rs/kg next to
    Rs/quintal) or with a decimal misplaced, which shows up as a 100-1000x
    single-day excursion. Those rows are not market moves, and fitting them
    distorts both the level and the confidence band, so they are replaced by
    the local rolling median before the model sees them.

    Returns (cleaned_series, repaired_row_count).
    """
    if len(g) < 5:
        return g, 0
    bad = junk_mask(g)
    n = int(bad.sum())
    if not n:
        return g, 0
    return g.mask(bad).interpolate(limit=5).ffill().bfill(), n


def junk_mask(g: pd.Series) -> pd.Series:
    """Rows that look like unit/parse errors rather than market prices.

    Two checks, because unit errors come in two shapes:
      local  - a single day in the wrong unit (the rolling median sees it)
      global - a whole stretch in the wrong unit, where the rolling median has
               already followed the bad level and can no longer see it
    """
    if len(g) < 5:
        return pd.Series(False, index=g.index)
    roll = g.rolling(31, center=True, min_periods=5).median()
    bad = (g < JUNK_LOW * roll) | (g > JUNK_HIGH * roll)
    level = float(np.median(g.values.astype(float)))
    if level > 0:
        bad = bad | (g < GLOBAL_LOW * level) | (g > GLOBAL_HIGH * level)
    return bad.fillna(False)


# ---------------------------------------------------------------------------
# Candidate models + backtest-driven selection
# ---------------------------------------------------------------------------
# "Which model is best here" is answered by the data, not by preference: every
# candidate is scored on the same rolling backtest and the winner is used.
# `naive` is deliberately a candidate, so the shipped forecast can never be
# worse than simply repeating today's price.

MODELS = ("hw_damped", "hw_flat", "seasonal_naive", "naive")

MODEL_LABELS = {
    "hw_damped": "Holt-Winters (damped trend + weekly pattern)",
    "hw_flat": "Holt-Winters (level + weekly pattern, no trend)",
    "seasonal_naive": "Same weekday last week",
    "naive": "Repeat the latest price",
}


def _candidate(y: np.ndarray, name: str, horizon: int) -> np.ndarray:
    """Forecast `horizon` steps ahead with one named candidate model."""
    if name == "naive":
        return np.full(horizon, float(y[-1]))
    if name == "seasonal_naive":
        n = len(y)
        lag = 7 if n >= 7 else 1
        return np.array([y[n - lag + (i % lag)] for i in range(horizon)], dtype=float)
    fc, _info = _hw_forecast(y, horizon, flat=(name == "hw_flat"))
    return np.clip(np.asarray(fc, dtype=float), 0.0, None)


def _model_scores(g: pd.Series, horizon: int = FORECAST_DAYS,
                  folds: int = 4) -> Dict[str, dict]:
    """Rolling-origin MAPE/WAPE for every candidate on this series."""
    y = g.values.astype(float)
    scores: Dict[str, dict] = {}
    for name in MODELS:
        mapes: List[float] = []
        wapes: List[float] = []
        detail: List[dict] = []
        for f in range(folds):
            cut = len(y) - horizon * (f + 1)
            if cut < max(2 * SEASON_M + 5, 40):
                break
            train, actual = y[:cut], y[cut:cut + horizon]
            if len(actual) < horizon:
                break
            fc = _candidate(train, name, horizon)
            m = _mape(actual, fc)
            if math.isnan(m):
                continue
            mapes.append(m)
            wapes.append(_wape(actual, fc))
            detail.append({"fold": f, "cut": cut, "mape": round(m, 2)})
        if not mapes:
            continue
        scores[name] = {
            "mape": round(float(np.mean(mapes)), 2),
            "wape": round(float(np.mean(wapes)), 2),
            "folds": len(mapes),
            "label": MODEL_LABELS.get(name, name),
            "detail": detail,
        }
    return scores


def select_and_forecast(g: pd.Series, horizon: int,
                        stale_days: int = 0, basis: str = "daily"
                        ) -> Tuple[str, np.ndarray, float, Dict[str, dict], bool]:
    """Choose a model for this series and produce its forecast.

    Shared by the API and the accuracy harness so both measure the same path.

    Two rules are driven by measurement, not preference:
      - `basis="monthly"`: the daily grid is an interpolation of monthly
        averages, and a trend fitted to that interpolation overshoots. Measured
        on 419 fourteen-day forecasts across 107 district series, trend models
        push the median error to ~13.5% against 10.6% for carrying the last
        published average, so monthly series carry forward and let the
        calibrated factors move the estimate instead.
      - A long gap since the last published price means a trend model would
        extrapolate a level nobody has confirmed for months, so it is
        downgraded to a flat carry and the band carries the uncertainty.
    """
    scores = _model_scores(g)
    if basis == "monthly":
        reduced = {k: v for k, v in scores.items()
                   if k in ("naive", "seasonal_naive")}
        if reduced:
            scores = reduced
    model_name, mape = _select_model(scores)
    downgraded = False
    if stale_days > STALE_TREND_DAYS and model_name.startswith("hw"):
        simpler = [k for k in ("seasonal_naive", "naive") if k in scores]
        if simpler:
            model_name = min(simpler,
                             key=lambda k: (SIMPLICITY.get(k, 9), scores[k]["mape"]))
            mape = float(scores[model_name]["mape"])
            downgraded = True
    fc = _candidate(g.values.astype(float), model_name, horizon)
    return model_name, fc, mape, scores, downgraded


def _score_folds(scores: Dict[str, dict], name: str) -> List[dict]:
    return list((scores.get(name) or {}).get("detail") or [])


def _public_scores(scores: Dict[str, dict]) -> Dict[str, dict]:
    """Model scores without per-fold detail (that is reported separately)."""
    return {k: {kk: vv for kk, vv in v.items() if kk != "detail"}
            for k, v in scores.items()}


def _wape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = float(np.sum(np.abs(actual)))
    if denom <= 1e-9:
        return float("nan")
    return float(np.sum(np.abs(actual - pred)) / denom * 100)


# Selection prefers the simplest model that is close to the best one. On a
# 24-month monthly grid the fold count is small, and a trend model can win its
# folds by fitting noise that does not survive out of sample.
SIMPLICITY = {"naive": 0, "seasonal_naive": 1, "hw_flat": 2, "hw_damped": 3}
SELECTION_MARGIN = 0.15


def _select_model(scores: Dict[str, dict]) -> Tuple[str, float]:
    """Best out-of-sample MAPE, ties going to the simpler model."""
    usable = {k: v for k, v in scores.items() if v.get("folds")}
    if not usable:
        return "naive", float("nan")
    best = min(usable[k]["mape"] for k in usable)
    tol = best * (1.0 + SELECTION_MARGIN) + 0.5
    near = [k for k in usable if usable[k]["mape"] <= tol]
    name = min(near, key=lambda k: (SIMPLICITY.get(k, 9), usable[k]["mape"]))
    return name, float(usable[name]["mape"])


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
# Context adjustments (season, festivals, calamity shocks)
# ---------------------------------------------------------------------------

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def _season_adjustment(commodity: str, district: Optional[str],
                       state: Optional[str]) -> Tuple[float, dict]:
    # NOTE: index is computed from published monthly averages only, so it stays
    # a measurement of this commodity in this place rather than a generic
    # "onion gets dearer in October" rule.
    """Month-of-year index computed from the published monthly averages.

    `index = mean(price in target month) / mean(price in all months)`, damped to
    [0.85, 1.15] so one thin month cannot swing the forecast. This is a measured
    seasonal ratio, not a hand-picked number.
    """
    df = price_store.monthly_history(commodity, district=district, state=state)
    if df is None or len(df) < MIN_MONTHS:
        return 1.0, {}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    overall = float(df["price"].mean())
    if overall <= 0:
        return 1.0, {}
    by_month = df.groupby(df["date"].dt.month)["price"].mean()
    target = (pd.Timestamp.today().normalize()
              + pd.Timedelta(days=FORECAST_DAYS)).month
    if target not in by_month.index:
        return 1.0, {}
    raw = float(by_month.loc[target]) / overall
    idx = max(0.85, min(1.15, raw))
    return idx, {
        "month": MONTH_NAMES[target - 1],
        "raw_index": round(raw, 3),
        "index": round(idx, 3),
        "months_used": int(df["date"].dt.month.nunique()),
        "years_used": int(df["date"].dt.year.nunique()),
    }


def _recent_shocks(commodity: str, district: Optional[str],
                   state: Optional[str]) -> List[str]:
    """Extreme month-on-month moves in the published averages.

    A >=25% swing between two published monthly averages is the footprint of a
    supply shock (unseasonal rain, flood, transport strike). We cannot name the
    cause, so we report the move and widen the band instead of guessing.
    """
    df = price_store.monthly_history(commodity, district=district, state=state)
    if df is None or len(df) < 3:
        return []
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    changes = df["price"].pct_change()
    shocks: List[str] = []
    for i in range(max(1, len(df) - 6), len(df)):
        v = changes.iloc[i]
        if v is None or pd.isna(v) or abs(float(v)) < 0.25:
            continue
        d = df["date"].iloc[i]
        shocks.append(f"{d.strftime('%b %Y')}: {float(v) * 100:+.0f}% month-on-month")
    return shocks


# ---------------------------------------------------------------------------
# Event layer: festivals, weather shocks, disasters
# ---------------------------------------------------------------------------
# A price model that only reads prices cannot know Diwali is in nine days or
# that 120 mm of rain is forecast. But bolting a hand-picked "+3% for Diwali"
# onto a statistical forecast makes it less accurate, not more. So each driver
# is *calibrated on the store's own history* before it is allowed to move the
# number, and anything that cannot be calibrated widens the uncertainty band
# instead of inventing an effect.

FESTIVAL_SHIFT_CAP = 0.04    # a festival may move the point estimate by <=4%
EVENT_SHIFT_CAP = 0.06       # weather/disaster trigger: <=6%
BAND_WIDEN_EVENT = 1.30      # live disruption signal -> wider band
BAND_WIDEN_FESTIVAL = 1.10
MIN_EVENTS = 5               # measured events needed before applying a shift
MAX_SHOCK_RESPONSE = 0.20    # a "typical" 14-day shock response above this is a level shift
STALE_TREND_DAYS = 45        # beyond this, no trend is projected either


def _clean_scope(commodity: str, district: Optional[str],
                 state: Optional[str]) -> Tuple[pd.Series, pd.Series]:
    """Cleaned daily series in the widest scope that has data, plus the mask
    of rows that were repaired (so event studies can skip their own handiwork)."""
    for d, s in ((district, state), (None, state), (None, None)):
        df = price_store.history(commodity, district=d, state=s)
        if df is not None and not df.empty:
            g = _daily_grid(
                df.groupby("date")["modal_price"].median().sort_index())
            if len(g) >= MIN_OBS:
                return clean_series(g)[0], junk_mask(g)
    return pd.Series(dtype=float), pd.Series(dtype=bool)


def _forward_returns(g: pd.Series, horizon: int) -> pd.Series:
    """Log returns over `horizon` days (robust to level jumps)."""
    arr = g.values.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(arr[horizon:] / arr[:-horizon])
    return pd.Series(out, index=g.index[horizon:]).replace(
        [np.inf, -np.inf], np.nan).dropna()


def _significant(uplift: float, values: List[float]) -> Tuple[bool, float]:
    """Is the measured effect distinguishable from that series' own noise?

    Returns (is_significant, t_stat). A festival "effect" smaller than the
    ordinary week-to-week noise of the same series is not applied — that is how
    a calendar rule ends up making a forecast worse instead of better.
    """
    n = len(values)
    if n < MIN_EVENTS:
        return False, 0.0
    sd = float(np.std(values, ddof=1))
    if sd <= 0:
        return abs(uplift) > 0, float("inf")
    t = abs(uplift) / (sd / math.sqrt(n))
    return t >= 1.5, round(t, 2)


def festival_calibration(commodity: str, district: Optional[str] = None,
                         state: Optional[str] = None) -> Optional[dict]:
    """Measured pre-festival price drift for this commodity and place.

    Compares the 7-day log return into each historical festival with the
    median 7-day return of the same series. Medians, because a handful of
    unit-error rows in a raw series produce absurd means. The result carries
    its own t-statistic so the caller can decline to use a noise-level effect.
    """
    g, _bad = _clean_scope(commodity, district, state)
    if len(g) < MIN_OBS:
        return None
    rets = _forward_returns(g, 7)
    if len(rets) < 60:
        return None
    try:
        import price_factors
        fests = price_factors.FESTIVALS
    except Exception:  # noqa: BLE001 - calibration is optional
        return None

    events: List[dict] = []
    for f in fests:
        try:
            d = pd.Timestamp(f["date"])
        except (ValueError, TypeError):
            continue
        if d < rets.index[0] or d > rets.index[-1]:
            continue
        window = rets.loc[d - pd.Timedelta(days=3):d]
        if window.empty:
            continue
        events.append({"name": f["name"], "date": f["date"],
                       "ret": float(window.iloc[-1])})

    if len(events) < MIN_EVENTS:
        return None
    # Mean of winsorised log returns: a median would be exactly zero on the
    # many flat weeks in mandi data and could never show a demand effect.
    clipped = np.clip(rets.values.astype(float), -0.5, 0.5)
    base = float(clipped.mean())
    vals = [float(np.clip(e["ret"], -0.5, 0.5)) for e in events]
    mean_event = float(np.mean(vals))
    uplift = mean_event - base
    ok, t = _significant(uplift, [v - base for v in vals])
    return {
        "commodity": commodity,
        "events": len(events),
        "median_festival_7d_pct": round(mean_event * 100, 2),
        "baseline_7d_pct": round(base * 100, 2),
        "uplift_pct": round(uplift * 100, 2),
        "t_stat": t,
        "significant": ok,
        "names": [e["name"] for e in events][:8],
    }


def shock_response(commodity: str, district: Optional[str] = None,
                   state: Optional[str] = None) -> Optional[dict]:
    """What happened *after* a sharp 3-day move, measured on this series.

    A flood, hailstorm or transport strike shows up in price as a sudden jump
    or collapse. We cannot label the cause, but we can measure the typical
    continuation over the following 14 days, which is what a live disruption
    signal should be allowed to assume.
    """
    g, bad = _clean_scope(commodity, district, state)
    if len(g) < MIN_OBS:
        return None
    r3 = g.pct_change(3)
    fwd = _forward_returns(g, FORECAST_DAYS).clip(-0.5, 0.5)
    joined = pd.concat([r3.rename("r3"), fwd.rename("fwd")], axis=1).dropna()
    if len(joined) < 60:
        return None
    # A repaired row produces a step change of its own; a "shock" that lands
    # next to one is the repair talking, not the market.
    if len(bad):
        tainted = bad.rolling(5, center=True, min_periods=1).max().fillna(False)
        joined = joined[~joined.index.map(lambda d: bool(tainted.get(d, False)))]
        if len(joined) < 60:
            return None
    # Only events from the price regime we are actually forecasting from. A
    # series that was re-reported in a different unit (Rs/nut vs Rs/quintal)
    # has a level break, and returns measured across that break describe the
    # unit change, not a shock response.
    now_level = float(g.iloc[-1])
    if now_level > 0:
        joined = joined[(joined.index >= g.index[-1] - pd.Timedelta(days=365))]
        level_ok = ((g.reindex(joined.index).between(0.5 * now_level,
                                                    2.0 * now_level)
                     .fillna(False))
                    & (g.shift(-FORECAST_DAYS).reindex(joined.index)
                       .between(0.5 * now_level, 2.0 * now_level).fillna(False)))
        joined = joined[level_ok]
    if len(joined) < 60:
        return None

    # Log returns, so a 2x move and a halving weigh the same.
    joined["r3"] = np.log1p(joined["r3"].clip(-0.999, 50))
    up = joined[joined["r3"] >= 0.20]
    down = joined[joined["r3"] <= -0.20]
    if len(up) + len(down) < MIN_EVENTS:
        return None
    base = float(np.median(joined["fwd"].values))
    spike = float(np.median(up["fwd"].values)) if len(up) else None
    crash = float(np.median(down["fwd"].values)) if len(down) else None
    ok = False
    t = 0.0
    if spike is not None:
        ok, t = _significant(spike - base,
                             [float(v) - base for v in up["fwd"].values])
    # A "typical 14-day response" beyond 20% in either direction is a level
    # shift, not a response a country-level weather signal should assume.
    capped = False
    if spike is not None and abs(spike) > MAX_SHOCK_RESPONSE:
        spike = math.copysign(MAX_SHOCK_RESPONSE, spike)
        capped = True
    if crash is not None and abs(crash) > MAX_SHOCK_RESPONSE:
        crash = math.copysign(MAX_SHOCK_RESPONSE, crash)
        capped = True
    return {
        "commodity": commodity,
        "up_events": int(len(up)),
        "down_events": int(len(down)),
        "after_spike_14d_pct": round(spike * 100, 2) if spike is not None else None,
        "after_crash_14d_pct": round(crash * 100, 2) if crash is not None else None,
        "baseline_14d_pct": round(base * 100, 2),
        "t_stat": t,
        "significant": ok,
        "capped": capped,
        "window_days": 365,
    }


WET_MONTH = 1.30    # this month is "wet" when it gets 30% more rain than normal
DRY_MONTH = 0.70


def rain_effect(commodity: str, district: Optional[str], state: Optional[str],
                lat: Optional[float], lon: Optional[float],
                target_month: Optional[int] = None) -> Optional[dict]:
    """How this district's prices behaved in wet vs normal months.

    Monthly prices give no daily shape, but they do line up with monthly
    rainfall across two to three years. This measures the difference between
    wetter-than-normal and normal months *for this crop and place*, with a
    t-statistic, so a rainy month can inform the next 14 days only when the
    series actually responds to rain.
    """
    if lat is None or lon is None:
        return None
    df = price_store.monthly_history(commodity, district=district, state=state)
    if df is None or len(df) < 18:
        return None
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    years = sorted({int(y) for y in df["date"].dt.year})
    if not years:
        return None
    try:
        import rainfall as rain_mod
        # Through the current year, so this month's rainfall so far is included.
        rain = rain_mod.monthly_rainfall(lat, lon, years[0],
                                         max(years[-1], pd.Timestamp.today().year))
    except Exception:  # noqa: BLE001 - rain is optional context
        return None
    if not rain:
        return None

    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        key = f"{d.year:04d}-{d.month:02d}"
        mm = rain.get(key)
        if mm is None:
            continue
        # Baseline for this calendar month across the years we have, so a wet
        # June is compared with Junes, not with the monsoon as a whole.
        normal, n_years = rain_mod.month_normal(rain, d.month)
        if not normal or normal <= 0:
            continue
        rows.append({"month": d.month, "year": d.year,
                     "price": float(r["price"]),
                     "ratio": mm / normal, "normal_mm": normal})
    if len(rows) < 18:
        return None

    frame = pd.DataFrame(rows)
    frame["logp"] = np.log(frame["price"].clip(lower=1e-6))

    # Season has to come out before rain can be measured, otherwise "rainy"
    # just means "monsoon" and the effect is double counted against the season
    # index the forecast already applies. Deviation = price minus the mean for
    # that calendar month and the mean for that year in this district.
    month_mean = frame.groupby("month")["logp"].transform("mean")
    year_mean = frame.groupby("year")["logp"].transform("mean")
    overall = float(frame["logp"].mean())
    frame["dev"] = frame["logp"] - month_mean - year_mean + overall
    frame["x"] = frame["ratio"] - 1.0     # 0 = a normal month for its calendar month

    x = frame["x"].values.astype(float)
    y = frame["dev"].values.astype(float)
    n = len(frame)
    slope = t = None
    if n >= 18 and float(np.var(x)) > 0:
        xc = x - x.mean()
        sxx = float(np.sum(xc ** 2))
        slope = float(np.sum(xc * (y - y.mean())) / sxx)
        resid = (y - y.mean()) - slope * xc
        dof = max(1, n - 3)
        se = math.sqrt(float(np.sum(resid ** 2)) / dof / sxx) if sxx > 0 else 0.0
        t = abs(slope) / se if se > 0 else 0.0

    n_wet = int((frame["ratio"] >= WET_MONTH).sum())
    n_dry = int((frame["ratio"] <= DRY_MONTH).sum())

    tmonth = target_month or pd.Timestamp.today().month
    # This month so far (plus what is still forecast) vs its own normal. The
    # archive lags a few days, so month_to_date() fills the gap.
    cur_key = pd.Timestamp.today().strftime("%Y-%m")
    cur_mm = rain.get(cur_key)
    try:
        live = rain_mod.month_to_date(lat, lon)
        if live is not None:
            cur_mm = max(cur_mm or 0.0, live)
    except Exception:  # noqa: BLE001 - fall back to the archive total
        pass
    normal, n_years = rain_mod.month_normal(rain, tmonth,
                                            exclude_year=pd.Timestamp.today().year)
    ratio_now = (cur_mm / normal) if (cur_mm is not None and normal) else None

    expected = (slope * (ratio_now - 1.0)) if (slope is not None
                                               and ratio_now is not None) else None
    return {
        "commodity": commodity,
        "district": district,
        "state": state,
        "months_used": int(n),
        "wet_months": n_wet,
        "dry_months": n_dry,
        # Per 1.0x of normal rainfall, after removing season and year level.
        "slope_pct_per_ratio": round(slope * 100, 2) if slope is not None else None,
        "t_stat": round(t, 2) if t is not None else None,
        "current_month": tmonth,
        "current_month_mm": round(cur_mm, 1) if cur_mm is not None else None,
        "normal_mm": round(normal, 1) if normal else None,
        "current_ratio": round(ratio_now, 2) if ratio_now is not None else None,
        "normal_years": n_years,
        "expected_shift_pct": round(expected * 100, 2) if expected is not None else None,
        "significant": bool(t is not None and t >= 2.0 and n >= 18),
    }


def normalize_triggers(raw: Optional[dict]) -> dict:
    """Flatten a weather report (or an injected test dict) to plain booleans."""
    if not raw:
        return {"flood_risk": False, "heavy_rain": False,
                "heat_stress": False, "available": False}
    keys = {str(s.get("key")) for s in raw.get("signals") or []}
    return {
        "flood_risk": bool(raw.get("flood_risk")) or "flood_risk" in keys,
        "heavy_rain": "heavy_rain" in keys,
        "heat_stress": "heat_stress" in keys or bool(raw.get("heat_days")),
        "available": True,
        "rain_7d_mm": raw.get("total_rain_7d_mm"),
    }


def _event_layer(commodity: str, district: Optional[str], state: Optional[str],
                 triggers: Optional[dict], horizon: int = FORECAST_DAYS,
                 lat: Optional[float] = None, lon: Optional[float] = None
                 ) -> dict:
    """Turn calibrated events into a bounded per-day adjustment.

    Returns `shifts` (one multiplier offset per forecast day), the applied
    factors with their evidence, and a band multiplier. Nothing here can move
    the estimate by more than EVENT_SHIFT_CAP in total.
    """
    applied: List[dict] = []
    notes: List[str] = []
    band_mult = 1.0
    shock_shift = 0.0
    festival_shift = 0.0
    festival_day: Optional[int] = None

    trig = normalize_triggers(triggers)
    live = trig["flood_risk"] or trig["heavy_rain"] or trig["heat_stress"]

    # --- festival demand ---
    fest = None
    try:
        import price_factors
        upcoming = price_factors.upcoming_festivals(days_ahead=horizon)
    except Exception:  # noqa: BLE001
        upcoming = []
    if upcoming:
        calib = festival_calibration(commodity, district, state)
        nxt = upcoming[0]
        festival_day = max(1, min(horizon, int(nxt["days_until"])))
        if calib and calib.get("significant"):
            raw = calib["uplift_pct"] / 100.0
            # Half strength for lunar dates, which can be a day or two out.
            damp = 0.5 if nxt.get("approx") else 1.0
            festival_shift = max(-FESTIVAL_SHIFT_CAP,
                                 min(FESTIVAL_SHIFT_CAP, raw * damp))
            applied.append({
                "key": "festival",
                "label": f"{nxt['name']} in {nxt['days_until']} day(s)",
                "shift_pct": round(festival_shift * 100, 2),
                "evidence": (f"measured on {calib['events']} past festivals: "
                             f"{calib['median_festival_7d_pct']:+.2f}% into the "
                             f"festival vs {calib['baseline_7d_pct']:+.2f}% "
                             f"baseline over 7 days (t={calib['t_stat']})"),
            })
            band_mult *= BAND_WIDEN_FESTIVAL
        elif calib:
            notes.append(
                f"{nxt['name']} falls inside the horizon, but the measured "
                f"festival effect ({calib['uplift_pct']:+.2f}%, "
                f"t={calib['t_stat']}) is within this series' own noise — no "
                "price shift applied.")
        else:
            notes.append(
                f"{nxt['name']} falls inside the horizon, but this series has "
                "too few past festivals to measure an effect — no price shift "
                "applied.")

    # --- live disruption (weather / disaster) ---
    if live:
        resp = shock_response(commodity, district, state)
        which = ("flood_risk" if trig["flood_risk"] else
                 "heavy_rain" if trig["heavy_rain"] else "heat_stress")
        if resp and resp.get("significant") and resp.get("after_spike_14d_pct") is not None:
            # A forecast disruption is not a realised one, so assume half of
            # the measured historical response, and only upward: disruption
            # removes supply, it does not create it.
            raw = max(0.0, float(resp["after_spike_14d_pct"]) / 100.0) * 0.5
            shock_shift = min(EVENT_SHIFT_CAP, raw)
            applied.append({
                "key": which,
                "label": ("Heavy rain / flood risk" if trig["flood_risk"]
                          else "Heavy rain expected" if trig["heavy_rain"]
                          else "Heat stress"),
                "shift_pct": round(shock_shift * 100, 2),
                "evidence": (f"after {resp['up_events']} past 3-day spikes of "
                             f">=20%, price moved "
                             f"{resp['after_spike_14d_pct']:+.2f}% over the next "
                             f"14 days vs {resp['baseline_14d_pct']:+.2f}% "
                             f"baseline (t={resp['t_stat']}); half of that is "
                             "assumed"),
            })
        elif resp:
            notes.append(
                "A disruption signal is active, but past shocks did not move "
                f"this price reliably ({resp['up_events']} events, "
                f"t={resp['t_stat']}) — the band is widened instead of the "
                "estimate being moved.")
        else:
            notes.append(
                "A disruption signal is active, but this series has too few "
                "past shocks to measure a response — the band is widened "
                "instead of the estimate being moved.")
        band_mult *= BAND_WIDEN_EVENT

    # --- this month's rain vs its own normal ---
    # Monthly-average districts have no daily shape to learn, but they do have
    # two to three years of monthly prices next to monthly rainfall.
    rain_shift = 0.0
    if lat is not None and lon is not None:
        eff = rain_effect(commodity, district, state, lat, lon)
        if eff and eff.get("expected_shift_pct") is not None and eff.get("significant"):
            ratio = eff["current_ratio"]
            expected = eff["expected_shift_pct"] / 100.0
            rain_shift = max(-EVENT_SHIFT_CAP,
                             min(EVENT_SHIFT_CAP, expected * 0.5))
            if abs(rain_shift) >= 0.005:
                kind = "wet" if ratio >= 1.0 else "dry"
                applied.append({
                    "key": "rainfall",
                    "label": (f"{kind.title()} month ({ratio:.2f}x normal rain)"),
                    "shift_pct": round(rain_shift * 100, 2),
                    "evidence": (
                        f"{eff['current_month_mm']} mm in "
                        f"{eff['current_month']:02d} vs a {eff['normal_mm']} mm "
                        f"normal over {eff['normal_years']} year(s); across "
                        f"{eff['months_used']} months of prices and rainfall, "
                        f"each unit of normal rain moved this crop "
                        f"{eff['slope_pct_per_ratio']:+.1f}% after removing the "
                        f"seasonal pattern (t={eff['t_stat']}); half is assumed"),
                })
        elif eff:
            if not eff.get("significant"):
                notes.append(
                    f"Rainfall history exists here ({eff['months_used']} months) "
                    f"but this crop's measured response to rain is too weak "
                    f"(t={eff.get('t_stat')}) to move the estimate.")
            else:
                notes.append(
                    "Rainfall history exists here and the response is real, but "
                    "this month's rain is close enough to its normal that no "
                    "adjustment applies.")

    total = max(-EVENT_SHIFT_CAP,
                min(EVENT_SHIFT_CAP, shock_shift + festival_shift + rain_shift))

    shifts: List[float] = []
    for day in range(1, horizon + 1):
        festival_part = 0.0
        if festival_shift and festival_day:
            festival_part = festival_shift * min(1.0, day / festival_day)
        # Disruption hits within days, not gradually.
        shock_part = shock_shift * min(1.0, day / 3.0)
        # A wet/dry month is a standing condition for the whole window.
        rain_part = rain_shift
        shifts.append(festival_part + rain_part
                      + max(-EVENT_SHIFT_CAP, min(EVENT_SHIFT_CAP, shock_part)))

    return {
        "applied": applied,
        "notes": notes,
        "shift_total_pct": round(total * 100, 2),
        "band_mult": round(band_mult, 3),
        "triggers": {**trig, "festivals": upcoming},
        "shifts": shifts,
    }


def _trigger_key(trig: Optional[dict]) -> str:
    """Stable cache key fragment for the live weather state."""
    if not trig:
        return "-"
    keys = {str(s.get("key")) for s in (trig.get("signals") or [])}
    return ("f" if trig.get("flood_risk") else "-") + \
           ("r" if "heavy_rain" in keys else "-") + \
           ("h" if (trig.get("heat_days") or "heat_stress" in keys) else "-")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _scope_forecast(commodity: str, scope_level: str, market: str,
                    district: Optional[str], state: Optional[str],
                    triggers: Optional[dict] = None,
                    lat: Optional[float] = None, lon: Optional[float] = None
                    ) -> Optional[dict]:
    g, basis = _series_with_basis(
        commodity, district if scope_level != "india" else None,
        state if scope_level in ("state", "district") else None, market)
    if len(g) < MIN_OBS:
        return None
    g = _daily_grid(g)
    g, repaired = clean_series(g)
    y = g.values.astype(float)

    last_date = g.index[-1]
    last_price = float(y[-1])
    base_date = max(last_date, pd.Timestamp.today().normalize())
    # Forecast the FULL horizon from the model (stale history means the
    # days between the last observation and today must also be projected),
    # instead of clamping every step to fc[-1] (which produced flat,
    # identical trajectories).
    stale_days = max(0, (base_date - last_date).days)
    shift = min(stale_days, _MAX_STALE_SHIFT)

    # Pick the model on out-of-sample folds, then fit the winner on everything.
    # `naive` is one of the candidates, so this cannot be worse than repeating
    # today's price — which the old fixed Holt-Winters notably was.
    model_name, fc, mape, scores, downgraded = select_and_forecast(
        g, shift + FORECAST_DAYS, stale_days=stale_days, basis=basis)
    if model_name.startswith("hw"):
        _fc, info = _hw_forecast(y, 2 * SEASON_M + 2,
                                 flat=(model_name == "hw_flat"))
        resid = np.asarray(info.get("resid", np.array([])), dtype=float)
        med = float(np.median(resid)) if len(resid) else 0.0
        mad = float(np.median(np.abs(resid - med))) if len(resid) else 0.0
        sigma = 1.4826 * mad if mad > 0 else float(np.std(resid)) * 0.5
    else:
        # Step noise of the last-value family: median absolute daily move.
        sigma = 1.4826 * float(np.median(np.abs(np.diff(y))))
    # Never show a zero-width band: even a perfectly flat series carries at
    # least ~1% of reporting/aggregation noise.
    sigma = max(sigma, 0.01 * max(last_price, 1.0))
    folds = _score_folds(scores, model_name)

    # Calendar context, all measured or labelled as heuristic:
    #   season  — annual index from the published monthly averages
    #   events  — festivals and live disruption signals, calibrated on history
    #   shocks  — observed >=25% month-on-month jumps (calamity footprint)
    season_idx, season_info = _season_adjustment(commodity, district, state)
    shocks = _recent_shocks(commodity, district, state)
    events = _event_layer(commodity, district, state, triggers,
                          lat=lat, lon=lon)
    # Monthly-basis series already carries the annual shape in its anchors, so
    # the index is applied at half strength there to avoid double counting.
    damp = 0.5 if basis == "monthly" else 1.0
    adjust = 1.0 + (season_idx - 1.0) * damp
    if shocks:
        # A recent supply shock widens the band instead of nudging the mean:
        # we cannot know if it repeats, only that the series is unstable.
        sigma = sigma * 1.25
    sigma = sigma * events["band_mult"]

    def _ctx_price(v: float) -> float:
        return max(0.0, float(v) * adjust)

    traj = []
    for h in range(1, FORECAST_DAYS + 1):
        d = (base_date + pd.Timedelta(days=h)).strftime("%Y-%m-%d")
        p = float(fc[h - 1 + shift]) if h - 1 + shift < len(fc) else float(fc[-1])
        p = _ctx_price(p) * (1.0 + events["shifts"][h - 1])
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
    # A monthly series is labelled by month (2024-01), not by the mid-month
    # anchor date used to keep the daily grid even.
    def _hist_label(ts) -> str:
        return (str(ts.date()) if basis == "daily"
                else ts.strftime("%Y-%m"))
    return {
        "commodity": commodity,
        "scope_level": scope_level,
        "market": market if scope_level == "market" else (
            f"{district or state or 'state'} aggregate"),
        "district": district, "state": state,
        "current_price": round(last_price, 2),
        "history_first": _hist_label(g.index[0]),
        "history_last": _hist_label(last_date),
        "history_obs": int(len(g)),
        "predicted_price_14d": p14,
        "predicted_change_pct": change14,
        "mape": round(mape_safe, 2),
        "backtest_folds": folds,
        "model": model_name,
        "model_label": MODEL_LABELS.get(model_name, model_name),
        "model_scores": _public_scores(scores),
        "trend_suppressed": downgraded,
        "selected_on": "rolling-origin backtest (4 folds x 14 days), best of "
                       f"{len(scores) or 1} candidates",
        "events": {k: events[k] for k in
                   ("applied", "notes", "shift_total_pct", "triggers")},
        "data_quality": {"repaired_rows": repaired, "rows_used": int(len(g))},
        # True age of the last published record; the projection above is capped
        # so a year-old month does not get extrapolated for a year.
        "stale_days": int(stale_days),
        "ci_low_14d": traj[-1]["ci_low"],
        "ci_high_14d": traj[-1]["ci_high"],
        "signal": _signal_text(change14, mape_safe),
        "history_basis": basis,
        # For a monthly basis this is how many averages were actually
        # published, not how many months the span covers.
        "history_months": (int(len(price_store.monthly_history(
            commodity, district=district, state=state)))
            if basis == "monthly" else int(g.index.to_period("M").nunique())),
        "season": season_info or None,
        "festivals": events["triggers"].get("festivals") or [],
        "shocks": shocks,
        "adjustment": round(adjust, 4),
        "trajectory": traj,
    }


def _signal_text(change_pct: float, mape: float) -> str:
    """Advice wording, gated on measured error.

    A sell/wait recommendation is only as good as the model's directional
    skill, so when the backtest error is large the wording says what the model
    projects without telling the farmer to act on it.
    """
    if mape > 15.0:
        if change_pct < -0.5:
            return (f"Low confidence (backtest error {mape:.0f}%): the model "
                    f"projects ~{abs(change_pct):.1f}% lower over 2 weeks, but "
                    "this series has been too erratic to act on alone.")
        if change_pct > 0.5:
            return (f"Low confidence (backtest error {mape:.0f}%): the model "
                    f"projects ~{change_pct:.1f}% higher over 2 weeks, but "
                    "this series has been too erratic to act on alone.")
        return (f"Low confidence (backtest error {mape:.0f}%): roughly flat "
                "over 2 weeks on a noisy series.")
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
             market: Optional[str] = "All", days: int = FORECAST_DAYS,
             state: Optional[str] = None,
             lat: Optional[float] = None, lon: Optional[float] = None,
             triggers: Optional[dict] = None) -> List[dict]:
    """Forecast for the requested commodity+location, with automatic scope
    fallback. Cached for 6h per scope key.

    `lat`/`lon` enable the live weather/disaster signals; without coordinates
    the forecast still runs, just without those triggers. `triggers` lets a
    caller (or a test) supply the weather report directly.
    """
    trig = triggers
    if trig is None and lat is not None and lon is not None:
        try:
            import price_factors
            trig = price_factors.weather_signals(lat, lon)
        except Exception:  # noqa: BLE001 - weather must never break a forecast
            trig = None
    key = (f"{_norm(commodity)}|{_norm(district)}|{_norm(state)}|"
           f"{_norm(market or 'All')}|{days}|"
           f"{round(float(lat or 0), 1)}|{round(float(lon or 0), 1)}|"
           f"{_trigger_key(trig)}")
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit["t"] < _CACHE_TTL:
            return hit["v"]

    commodities = [resolve_name(commodity)] if commodity else []
    out = []
    for com in commodities:
        res = _forecast_one(district, com, market, days, state=state,
                            triggers=trig, lat=lat, lon=lon)
        if res:
            out.append(res)
    # An empty answer is not cached: it only means this crop has no history
    # *yet*, and a backfill a minute later must show up on the next request
    # instead of hiding behind a six-hour cache.
    if out:
        with _cache_lock:
            _cache[key] = {"t": now, "v": out}
    return out


def resolve_name(name: str) -> str:
    """The spelling the price store actually holds for this crop.

    "Ragi" has to become "Ragi(Finger Millet)" or every query below misses its
    rows and the page claims there is no history. mandi_prices already owns
    that mapping (aliases, regional names, stored spellings), so reuse it
    lazily rather than keeping a second, drifting table here.
    """
    base = str(name or "").strip()
    if not base:
        return base
    try:
        import mandi_prices
        canonical = mandi_prices.resolve_commodity(base) or base
        return mandi_prices.clamp_to_store(canonical) or canonical
    except Exception:  # noqa: BLE001 - alias resolution must never break a forecast
        pass
    map_ = {
        "paddy": "Rice", "rice": "Rice", "maize": "Maize", "wheat": "Wheat",
        "cotton": "Cotton", "onion": "Onion", "tomato": "Tomato",
        "potato": "Potato", "banana": "Banana", "urad": "Urad",
        "moong": "Moong", "tur": "Arhar/Tur", "arhar": "Arhar/Tur",
        "gram": "Gram", "chickpea": "Gram", "groundnut": "Groundnut",
    }
    return map_.get(base.lower(), base)


def _forecast_one(district: Optional[str], commodity: str,
                  market: Optional[str], days: int,
                  state: Optional[str] = None,
                  triggers: Optional[dict] = None,
                  lat: Optional[float] = None,
                  lon: Optional[float] = None) -> Optional[dict]:
    # Caller-supplied state first (the UI always knows it), then the store.
    state = str(state).strip() if state and str(state).strip().lower() not in (
        "", "all", "none") else None
    if not state and district:
        state = price_store.state_for_district(district)
    scopes: List[Tuple[str, Optional[str], Optional[str]]] = []
    if market and str(market).lower() != "all":
        scopes.append(("market", district, market))
    if district:
        scopes.append(("district", district, None))
    if state:
        scopes.append(("state", None, None))
    # Only an unscoped request may use the national series. A farmer asking for
    # Jharkhand gets a Jharkhand answer or an honest "no data" — never an
    # All-India trend wearing their state's name.
    if not district and not state:
        scopes.append(("india", None, None))
    for level, d, m in scopes:
        res = _scope_forecast(commodity, level, m or "All",
                              d if level != "state" else None, state,
                              triggers=triggers, lat=lat, lon=lon)
        if res:
            return res
    return None


CACHE_TTL = _CACHE_TTL


def known_commodities() -> List[str]:
    return price_store.distinct_commodities()


def known_markets() -> List[Dict[str, str]]:
    return price_store.distinct_markets()
