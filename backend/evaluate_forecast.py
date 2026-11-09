"""
Accuracy harness for the served price forecaster (price_forecast).

The API already reports a MAPE per response, but a MAPE alone says nothing: it
is only meaningful next to a baseline, measured the way the app is used
(1-14 days ahead, from a cut the model never saw).

This walks every district+commodity series in the real price store, runs a
rolling-origin backtest, and compares the shipped model against two honest
baselines:

  naive          - repeat today's price for every future day
  seasonal naive - repeat the price from 7 days ago

It reports WAPE (sum |error| / sum |actual|) alongside MAPE, because MAPE
explodes on the near-zero junk rows that exist in AGMARKNET data, and it runs
the comparison twice:

  raw     - exactly the series the API would use today
  cleaned - rows below 10% of the series median removed (a mandi price does not
            fall 90% in a day; those are unit/parse errors, not market moves)

Directional hit rate is reported too: the UI's sell/wait signal promises the
sign of the move ("prices likely to rise ~X%"), not the exact number.

Usage (from the repo root):
    ./collab/venv/bin/python Farm_intel/backend/evaluate_forecast.py
    ./collab/venv/bin/python Farm_intel/backend/evaluate_forecast.py --folds 6 --min-obs 200 --horizons 1,7,14
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

import price_store  # noqa: E402
import price_forecast as pf  # noqa: E402


def _series_pairs(min_obs: int):
    """(state, district, commodity) with enough daily history to judge."""
    price_store.init_db()
    with price_store._lock:
        conn = price_store._connect()
        rows = conn.execute(
            "SELECT state, district, commodity, COUNT(*) n FROM mandi_prices "
            "WHERE state != '' AND district != '' AND commodity != '' "
            "GROUP BY state, district, commodity HAVING n >= ? "
            "ORDER BY n DESC", (min_obs,)).fetchall()
    return [dict(r) for r in rows]


def _mape(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.abs(actual) > 1e-9
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100)


def _wape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = float(np.sum(np.abs(actual)))
    if denom <= 1e-9:
        return float("nan")
    return float(np.sum(np.abs(actual - pred)) / denom * 100)


def _directional(actual: np.ndarray, pred: np.ndarray) -> float:
    """Sign hit rate for the move over the horizon; NaN when the truth is flat."""
    a = actual[-1] - actual[0]
    p = pred[-1] - pred[0]
    if abs(a) < 0.02 * abs(actual[0] or 1):
        return float("nan")
    return 1.0 if (a > 0) == (p > 0) else 0.0


def _clean(y: np.ndarray) -> np.ndarray:
    """Drop rows below 10% of the series median (unit/parse errors)."""
    med = float(np.median(y))
    if med <= 0:
        return y
    return np.where(y < 0.1 * med, med, y)


def _backtest(y: np.ndarray, folds: int, h: int) -> dict:
    """Online backtest: the model is selected on data before each cut.

    This mirrors what the API does — choose the best candidate on history, then
    forecast — so the number reported here is the shipped behaviour rather than
    the old fixed Holt-Winters.
    """
    out = {"model_mape": [], "naive_mape": [], "seasonal_mape": [],
           "model_wape": [], "naive_wape": [], "dir": [], "picked": []}
    for f in range(folds):
        cut = len(y) - h * (f + 1)
        if cut < max(2 * pf.SEASON_M + 5, 40):
            break
        train, actual = y[:cut], y[cut:cut + h]
        if len(actual) < h:
            break
        scores = pf._model_scores(pd.Series(train), horizon=h, folds=2)
        name, _ = pf._select_model(scores)
        fc = np.asarray(pf._candidate(train, name, h), dtype=float)
        naive = np.full(h, train[-1])
        seasonal = np.array([train[-7 + (i % 7)] if len(train) >= 7 else train[-1]
                             for i in range(h)])
        out["model_mape"].append(_mape(actual, fc))
        out["naive_mape"].append(_mape(actual, naive))
        out["seasonal_mape"].append(_mape(actual, seasonal))
        out["model_wape"].append(_wape(actual, fc))
        out["naive_wape"].append(_wape(actual, naive))
        out["picked"].append(name)
        d = _directional(actual, fc)
        if not math.isnan(d):
            out["dir"].append(d)
    return out


def _summary(chunks: list[dict]) -> dict | None:
    merged: dict[str, list] = {}
    for c in chunks:
        for k, v in c.items():
            merged.setdefault(k, []).extend(v)
    if not merged.get("model_mape"):
        return None

    def med(key):
        a = np.array(merged[key], dtype=float)
        a = a[~np.isnan(a)]
        return (round(float(np.median(a)), 2), round(float(np.mean(a)), 2)) if len(a) else (None, None)

    model_mape, naive_mape = med("model_mape"), med("naive_mape")
    model_wape, naive_wape = med("model_wape"), med("naive_wape")
    beats = float(np.mean(np.array(merged["model_mape"]) < np.array(merged["naive_mape"])) * 100)
    picks: dict = {}
    for name in merged.get("picked", []):
        picks[name] = picks.get(name, 0) + 1
    return {
        "picks": picks,
        "folds": len(merged["model_mape"]),
        "mape_model": model_mape, "mape_naive": naive_mape,
        "mape_seasonal": med("seasonal_mape"),
        "wape_model": model_wape, "wape_naive": naive_wape,
        "beats_naive_pct": round(beats, 1),
        "directional_pct": (round(float(np.mean(merged["dir"])) * 100, 1)
                            if merged["dir"] else None),
    }


def _monthly_pairs(min_months: int):
    """Every district+commodity with enough *published monthly averages*.

    This is the data most districts are forecast from: the store holds ~3 years
    of AGMARKNET district monthly averages for 13 states, while two years of
    dense *daily* records exist only for Goa.
    """
    price_store.init_db()
    with price_store._lock:
        conn = price_store._connect()
        rows = conn.execute(
            "SELECT state, district, commodity, COUNT(*) n FROM mandi_monthly "
            "WHERE state != '' AND district != '' AND commodity != '' "
            "GROUP BY state, district, commodity HAVING n >= ? "
            "ORDER BY n DESC", (min_months,)).fetchall()
    return [dict(r) for r in rows]


def evaluate_monthly(min_months: int, folds: int) -> dict:
    """14-day accuracy when the history is monthly averages.

    This is exactly the served path for most districts: the published monthly
    averages are turned into a daily grid, the model is chosen on that grid, and
    the next 14 days are produced. The only observable truth for such a district
    is the next published monthly average, so the 14-day mean forecast is scored
    against it. Every prediction here is a *14-day* prediction, not a
    months-ahead one.
    """
    pairs = _monthly_pairs(min_months)
    rows = []
    for s in pairs:
        df = price_store.monthly_history(s["commodity"], district=s["district"],
                                         state=s["state"])
        if df is None or len(df) < min_months:
            continue
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        if float(np.median(df["price"])) <= 0:
            continue
        for k in range(1, folds + 1):
            if len(df) - k < min_months - 3:
                break
            train_df = df.iloc[:-k]
            target = df.iloc[-k]
            grid = pf.monthly_to_daily(train_df)
            if len(grid) < pf.MIN_OBS:
                continue
            # Days from the last published average to the start of the target
            # month, plus the 14 days we are predicting.
            start = target["date"].replace(day=1)
            shift = max(0, (start - grid.index[-1]).days)
            name, fc, _mape_sel, _scores, _dg = pf.select_and_forecast(
                grid, shift + 14, stale_days=shift, basis="monthly")
            fc = np.asarray(fc, dtype=float)
            pred_14 = float(np.mean(fc[-14:]))
            actual = float(target["price"])
            if actual <= 0 or pred_14 <= 0:
                continue
            last_month = float(train_df["price"].iloc[-1])
            last_year = (float(train_df["price"].iloc[-12])
                         if len(train_df) >= 12 else last_month)
            rows.append({
                "series": f"{s['district']}/{s['commodity']}",
                "state": s["state"],
                "model": name,
                "model_mape": abs(pred_14 - actual) / actual * 100,
                "naive_mape": abs(last_month - actual) / actual * 100,
                "last_year_mape": abs(last_year - actual) / actual * 100,
            })

    if not rows:
        return {"series": 0, "folds": 0}
    frame = pd.DataFrame(rows)
    picks: dict = {}
    for n in frame["model"]:
        picks[n] = picks.get(n, 0) + 1
    return {
        "series": int(frame["series"].nunique()),
        "folds": int(len(frame)),
        "states": int(frame["state"].nunique()),
        "model_mape": round(float(frame["model_mape"].median()), 2),
        "model_mape_mean": round(float(frame["model_mape"].mean()), 2),
        "naive_mape": round(float(frame["naive_mape"].median()), 2),
        "last_year_mape": round(float(frame["last_year_mape"].median()), 2),
        "beats_naive_pct": round(float((frame["model_mape"]
                                        < frame["naive_mape"]).mean() * 100), 1),
        "picks": picks,
    }


def evaluate(min_obs: int, folds: int, horizons: list[int]) -> dict:
    pairs = _series_pairs(min_obs)
    raw = {h: [] for h in horizons}
    cleaned = {h: [] for h in horizons}
    used, skipped = [], []

    for s in pairs:
        df = price_store.history(s["commodity"], district=s["district"],
                                 state=s["state"])
        if df.empty:
            continue
        g = pf._daily_grid(df.groupby("date")["modal_price"].median().sort_index())
        y = g.values.astype(float)
        if len(y) < min_obs:
            skipped.append(f"{s['district']}/{s['commodity']} ({len(y)}d)")
            continue
        last = g.index[-1]
        stale = (pd.Timestamp.today().normalize() - last).days
        used.append({"series": f"{s['district']}/{s['commodity']}",
                     "obs": int(len(y)),
                     "median": round(float(np.median(y))),
                     "stale_days": int(stale),
                     "corrupt_rows": int(np.sum(y < 0.1 * float(np.median(y))))})
        yc = _clean(y)
        for h in horizons:
            raw[h].append(_backtest(y, folds, h))
            cleaned[h].append(_backtest(yc, folds, h))

    return {"used": used, "skipped": skipped,
            "raw": {h: _summary(v) for h, v in raw.items()},
            "cleaned": {h: _summary(v) for h, v in cleaned.items()}}


def _print_table(title: str, table: dict) -> None:
    print(f"\n{title}")
    print(f"{'horizon':>7} {'folds':>6} {'model MAPE':>14} {'naive MAPE':>14} "
          f"{'model WAPE':>14} {'naive WAPE':>14} {'beats':>7} {'dir%':>6}")
    for h, v in table.items():
        if not v:
            print(f"{h:>7}  no usable folds")
            continue
        mm, mn = v["mape_model"], v["mape_naive"]
        wm, wn = v["wape_model"], v["wape_naive"]
        print(f"{h:>7}d {v['folds']:>5} "
              f"{mm[0]:>7.1f}/{mm[1]:<6.1f} "
              f"{mn[0]:>7.1f}/{mn[1]:<6.1f} "
              f"{wm[0]:>7.1f}/{wm[1]:<6.1f} "
              f"{wn[0]:>7.1f}/{wn[1]:<6.1f} "
              f"{v['beats_naive_pct']:>6.1f}% "
              f"{v['directional_pct'] if v['directional_pct'] is not None else float('nan'):>6.1f}"
              f"  {v.get('picks')}")
    print("(median/mean %, lower is better)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-obs", type=int, default=120)
    ap.add_argument("--min-months", type=int, default=18)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--horizons", type=str, default="1,7,14")
    ap.add_argument("--series", action="store_true", help="print per-series detail")
    args = ap.parse_args()
    horizons = [int(h) for h in args.horizons.split(",") if h.strip()]

    rep = evaluate(args.min_obs, args.folds, horizons)
    print(f"DAILY series evaluated: {len(rep['used'])}  "
          f"skipped (too short): {len(rep['skipped'])}")
    if args.series:
        print(pd.DataFrame(rep["used"]).to_string(index=False))
    else:
        print(pd.DataFrame(rep["used"]).head(10).to_string(index=False))
    _print_table("RAW series (what the API uses today)", rep["raw"])
    _print_table("CLEANED series (unit-error rows repaired)", rep["cleaned"])

    # The district monthly averages are what most states are forecast from.
    m = evaluate_monthly(args.min_months, max(2, args.folds))
    if m["folds"]:
        print(f"\nMONTHLY-basis districts: {m['series']} series, {m['states']} states, "
              f"{m['folds']} fourteen-day forecasts")
        print(f"  model 14-day MAPE  {m['model_mape']:>6.2f}% (mean {m['model_mape_mean']:.2f}%)")
        print(f"  repeat last month  {m['naive_mape']:>6.2f}%")
        print(f"  same month last yr {m['last_year_mape']:>6.2f}%")
        print(f"  beats last month   {m['beats_naive_pct']:>6.1f}%  {m['picks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
