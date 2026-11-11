"""
Train the district-aware crop recommendation model.

The app has always served `models/rf_model.pkl`, a RandomForest trained on the
public Kaggle "Crop Recommendation" table: seven climate columns (N, P, K,
temperature, humidity, pH, rainfall) and 22 crop labels, with no notion of
place. The district layer therefore had to bolt locality on afterwards with
hand-weighted terms.

`hybrid_crop_model/datasets/final_training_dataset.csv` ships the district-level
table this project already collected: 6,878 rows over 355 districts in 14
states, carrying each district's soil survey indices (n/p/k/ph, organic carbon,
salinity), its coordinates, its per-season climatology and the crops it grows.

Why the target is not "which one crop":

    within a (district, season) every row has an identical feature vector, and
    the label is a SET of ~5 crops that district grows. Treating it as
    13-way single-label classification is unlearnable - it scores ~0.006,
    because identical inputs carry different labels.

So the model is trained as a suitability scorer instead: one example per
(district, season, crop) with a binary label "this district grows this crop in
this season". At inference the same scorer ranks the candidate crops the
district layer already considers, which is exactly the quantity the app needs
(`ml_prob` per crop). It also learns across districts: soil, salinity and
climate bands transfer to a district nobody has data for.

Outputs:

    models/crop_model.pkl          bundle: model + crop vocabulary + feature
                                   order + per-district feature lookup + metrics
    reports/crop-model-report.md   what was measured, and how

Every model is scored two ways:

  * grouped by district - entire districts held out. The honest number, and the
    only situation where a model beats the existing lookup.
  * stratified - rows held out from districts the model has seen. Reported for
    completeness; it mostly measures memorisation.

Selection is on grouped precision@3, the metric the UI actually depends on
(the API shows the top 3-5 crops). Two non-ML references are measured alongside
so the numbers mean something: random guessing, the global crop-frequency
prior, and the nearest district's crop list.

Usage:

    python train_crop_model.py [--quick]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(BASE_DIR, "hybrid_crop_model", "datasets",
                       "final_training_dataset.csv")
MODELS_DIR = os.path.join(BASE_DIR, "models")
BUNDLE_PATH = os.path.join(MODELS_DIR, "crop_model.pkl")
REPORT_PATH = os.path.join(os.path.dirname(BASE_DIR), "reports",
                           "crop-model-report.md")

# Government aggregate buckets in the source table. They are sums over real
# crops ("Total Food Grains", "Cereals"), so a farmer cannot sow them and the
# recommendation code filters them out. Training on them would teach the model
# to predict a class the API must then discard.
AGGREGATE_LABELS = {
    "total food grains", "cereals", "nutri/coarse cereals",
    "shree anna /nutri cereals", "other pulses",
}

# District features, in the order the model expects them. `area`,
# `production` and `yield` are deliberately absent: they are outcomes of the
# crop being grown, so using them would leak the label.
DISTRICT_FEATURES: List[str] = [
    "n_index", "p_index", "k_index", "ph_index",
    "oc_high", "oc_medium", "oc_low", "ec_nonsaline", "ec_saline",
    "latitude", "longitude", "temp", "humidity", "rainfall",
    "season_rabi",
]

TOP_K = 3


def norm(name: str) -> str:
    """Same name folding the backend uses for districts and states."""
    out = str(name).strip().lower()
    for ch in ("\u2013", "\u2014", "-", "_", "(", ")", ".", ","):
        out = out.replace(ch, " ")
    return " ".join(out.split())


def load_training_frame() -> pd.DataFrame:
    df = pd.read_csv(DATASET)
    before = len(df)
    df = df[~df["crop"].str.strip().str.lower().isin(AGGREGATE_LABELS)].copy()
    df = df.dropna(subset=["crop", "district"] + DISTRICT_FEATURES[:14])
    df["crop"] = df["crop"].str.strip().str.lower()
    df["district_key"] = df["district"].map(norm)
    df["state_key"] = df["state"].map(norm)
    df["season"] = df["season"].str.strip().str.lower()
    df["season_rabi"] = (df["season"] == "rabi").astype(int)
    print(f"[train] {len(df)} of {before} rows kept "
          f"({before - len(df)} aggregate rows dropped)")
    return df


def district_lookup(df: pd.DataFrame) -> Dict[str, dict]:
    """
    Per-district feature values, for inference.

    Every soil and coordinate column is constant within a district in this
    table, so one row per district is enough. The district's climatology is
    kept per season as a fallback for when the API has no live weather.
    """
    lookup: Dict[str, dict] = {}
    for key, sub in df.groupby("district_key"):
        first = sub.iloc[0]
        lookup[key] = {
            "state": first["state_key"],
            "n_index": float(first["n_index"]),
            "p_index": float(first["p_index"]),
            "k_index": float(first["k_index"]),
            "ph_index": float(first["ph_index"]),
            "oc_high": float(first["oc_high"]),
            "oc_medium": float(first["oc_medium"]),
            "oc_low": float(first["oc_low"]),
            "ec_nonsaline": float(first["ec_nonsaline"]),
            "ec_saline": float(first["ec_saline"]),
            "latitude": float(first["latitude"]),
            "longitude": float(first["longitude"]),
            "climate": {
                season: {
                    "temp": float(g["temp"].mean()),
                    "humidity": float(g["humidity"].mean()),
                    "rainfall": float(g["rainfall"].mean()),
                }
                for season, g in sub.groupby("season")
            },
        }
    return lookup


def build_examples(df: pd.DataFrame, crops: List[str]
                   ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Expand (district, season) crop sets into one row per (pair, crop).

    A crop a district does not grow in that season becomes a negative example.
    Feature values are the district's own soil/coordinate/climate block plus a
    one-hot crop identity, so the model learns suitability, not a lookup.

    Returns (X, y, district_groups, pair_ids). `pair_ids` labels each row with
    its (district, season) so scoring can regroup a shuffled test split.
    """
    pairs = df.groupby(["district_key", "season"])
    district_block = df.drop_duplicates(
        ["district_key", "season"])[["district_key", "season"]
                                    + DISTRICT_FEATURES]
    crop_index = {c: i for i, c in enumerate(crops)}

    rows, labels, groups, pair_ids = [], [], [], []
    for (dkey, season), sub in pairs:
        base = district_block[(district_block["district_key"] == dkey)
                              & (district_block["season"] == season)]
        if base.empty:
            continue
        feats = base.iloc[0][DISTRICT_FEATURES].to_numpy(dtype=float)
        grown = set(sub["crop"])
        for crop in crops:
            oh = np.zeros(len(crops), dtype=float)
            oh[crop_index[crop]] = 1.0
            rows.append(np.concatenate([feats, oh]))
            labels.append(1 if crop in grown else 0)
            groups.append(dkey)
            pair_ids.append(f"{dkey}|{season}")
    return (np.asarray(rows, dtype=float), np.asarray(labels, dtype=int),
            np.asarray(groups), np.asarray(pair_ids))


def build_models(quick: bool, n_crops: int) -> Dict[str, object]:
    rf_trees = 150 if quick else 400
    xgb_rounds = 150 if quick else 500

    def rf() -> RandomForestClassifier:
        return RandomForestClassifier(
            n_estimators=rf_trees, max_depth=14, min_samples_leaf=4,
            class_weight="balanced_subsample", n_jobs=-1, random_state=42)

    models: Dict[str, object] = {"RandomForest": rf()}
    try:
        from xgboost import XGBClassifier

        def xgb() -> "XGBClassifier":
            return XGBClassifier(
                n_estimators=xgb_rounds, learning_rate=0.06, max_depth=5,
                subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
                objective="binary:logistic", eval_metric="logloss",
                tree_method="hist", n_jobs=-1, random_state=42, verbosity=0)

        models["XGBoost"] = xgb()
        models["Ensemble"] = VotingClassifier(
            estimators=[("rf", rf()), ("xgb", xgb())],
            voting="soft", n_jobs=-1)
    except ImportError:
        print("[train] xgboost not installed - comparing RandomForest only")
    return models


def evaluate_pairs(proba: np.ndarray, labels: np.ndarray,
                   pair_ids: np.ndarray, k: int = TOP_K) -> dict:
    """precision@k, recall@k and AUC over held-out (district, season) pairs.

    Groups by pair id rather than assuming the test rows arrive in pair order,
    so it is correct for a shuffled stratified split too.

    Precision is normalised by `min(k, crops grown)`. A stratified fold leaves
    only one or two of a pair's crops in the test set, and dividing by k would
    cap that pair at 1/3 no matter how good the ranking was - which is what
    made the stratified column look catastrophically worse than the grouped
    one. With districts held out entirely, classes per pair exceed k and this
    is the ordinary precision@3.
    """
    precisions, recalls = [], []
    for pid in pd.unique(pair_ids):
        mask = pair_ids == pid
        block = proba[mask]
        truth = labels[mask]
        if len(block) == 0 or truth.sum() == 0:
            continue
        got = truth[np.argsort(block)[::-1][:k]].sum()
        precisions.append(float(got) / min(k, int(truth.sum())))
        recalls.append(float(got) / max(1, int(truth.sum())))
    auc = np.nan
    if len(np.unique(labels)) > 1:
        auc = float(roc_auc_score(labels, proba))
    return {
        "precision_at_3": float(np.mean(precisions)),
        "recall_at_3": float(np.mean(recalls)),
        "auc": auc,
        "pairs": len(precisions),
    }


def nearest_district_baseline(pairs: pd.DataFrame, crops: List[str],
                              k: int = TOP_K) -> dict:
    """
    Reference: rank a district's crops by its nearest known district's list.

    This is the lookup the app already effectively does. Any model that cannot
    beat it is not worth wiring in.
    """
    coords = pairs[["district_key", "latitude", "longitude"]].drop_duplicates(
        "district_key").reset_index(drop=True)
    crop_index = {c: i for i, c in enumerate(crops)}
    precisions, recalls = [], []
    for (dkey, season), sub in pairs.groupby(["district_key", "season"]):
        mine = coords[coords["district_key"] == dkey].iloc[0]
        others = coords[coords["district_key"] != dkey]
        if others.empty:
            continue
        d2 = ((others["latitude"] - mine["latitude"]) ** 2
              + (others["longitude"] - mine["longitude"]) ** 2)
        neighbour = others.loc[d2.idxmin(), "district_key"]
        near = pairs[(pairs["district_key"] == neighbour)
                     & (pairs["season"] == season)]
        neigh_crops = set(near["crops"].iloc[0]) if not near.empty else set()
        scores = np.zeros(len(crops))
        for c in neigh_crops:
            scores[crop_index[c]] = 1.0
        truth = np.zeros(len(crops))
        for c in set(sub["crops"].iloc[0]):
            truth[crop_index[c]] = 1.0
        got = truth[np.argsort(scores)[::-1][:k]].sum()
        precisions.append(float(got) / min(k, int(truth.sum())))
        recalls.append(float(got) / max(1, int(truth.sum())))
    return {
        "precision_at_3": float(np.mean(precisions)),
        "recall_at_3": float(np.mean(recalls)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="smaller models for a fast smoke run")
    args = ap.parse_args()

    df = load_training_frame()
    crops = sorted(df["crop"].unique())
    X, y, groups, pair_ids = build_examples(df, crops)
    n_crops = len(crops)
    print(f"[train] {X.shape[0]} examples ({X.shape[1]} features), "
          f"{n_crops} crops, {df['district_key'].nunique()} districts, "
          f"{len(pd.unique(pair_ids))} district-season pairs")

    grouped_pairs = list(GroupKFold(n_splits=5).split(X, y, groups=groups))
    random_pairs = list(StratifiedKFold(n_splits=5, shuffle=True,
                                        random_state=42).split(X, y))

    metrics: Dict[str, dict] = {}
    for name, proto in build_models(args.quick, n_crops).items():
        print(f"[train] {name} ...", flush=True)
        per_split: Dict[str, list] = {"grouped": [], "stratified": []}
        for label, splits in (("grouped", grouped_pairs),
                              ("stratified", random_pairs)):
            for tr, te in splits:
                proto.fit(X[tr], y[tr])
                proba = proto.predict_proba(X[te])[:, 1]
                per_split[label].append(
                    evaluate_pairs(proba, y[te], pair_ids[te]))
        metrics[name] = {
            "grouped_by_district": {
                "precision_at_3": float(np.mean(
                    [s["precision_at_3"] for s in per_split["grouped"]])),
                "precision_std": float(np.std(
                    [s["precision_at_3"] for s in per_split["grouped"]])),
                "recall_at_3": float(np.mean(
                    [s["recall_at_3"] for s in per_split["grouped"]])),
                "auc": float(np.nanmean([s["auc"] for s in per_split["grouped"]])),
            },
            "stratified": {
                "precision_at_3": float(np.mean(
                    [s["precision_at_3"] for s in per_split["stratified"]])),
                "recall_at_3": float(np.mean(
                    [s["recall_at_3"] for s in per_split["stratified"]])),
                "auc": float(np.nanmean(
                    [s["auc"] for s in per_split["stratified"]])),
            },
        }
        g = metrics[name]["grouped_by_district"]
        s = metrics[name]["stratified"]
        print(f"[train] {name}: grouped P@3 {g['precision_at_3']:.3f} "
              f"(recall@3 {g['recall_at_3']:.3f}, AUC {g['auc']:.3f}) | "
              f"stratified P@3 {s['precision_at_3']:.3f}")

    # References measured on the same pairs.
    pairs = df.groupby(["district_key", "season"]).agg(
        latitude=("latitude", "first"), longitude=("longitude", "first"),
        crops=("crop", lambda s: sorted(set(s)))).reset_index()
    baseline_nn = nearest_district_baseline(pairs, crops)
    positive_rate = float(y.mean())
    # Expected precision@3 of a random ranking, under the same
    # min(k, grown) normalisation the models are scored with.
    random_precision = float(np.mean([
        (TOP_K * len(r["crops"]) / n_crops) / min(TOP_K, len(r["crops"]))
        for _, r in pairs.iterrows()]))
    # Ranking crops by how often they appear overall, before any features.
    freq = df["crop"].value_counts(normalize=True)
    freq_precisions = []
    for _, r in pairs.iterrows():
        order = [c for c in freq.index if c in crops][:TOP_K]
        got = sum(1 for c in order if c in r["crops"])
        freq_precisions.append(got / min(TOP_K, len(r["crops"])))
    baseline_freq = {"precision_at_3": float(np.mean(freq_precisions))}
    print(f"[train] baselines: nearest district P@3 "
          f"{baseline_nn['precision_at_3']:.3f}, crop frequency P@3 "
          f"{baseline_freq['precision_at_3']:.3f}")

    best_name = max(metrics, key=lambda n: (
        metrics[n]["grouped_by_district"]["precision_at_3"],
        metrics[n]["grouped_by_district"]["auc"]))
    print(f"[train] best by grouped P@3: {best_name}")

    best = build_models(args.quick, n_crops)[best_name]
    best.fit(X, y)

    importances = None
    feature_names = DISTRICT_FEATURES + [f"crop_{c}" for c in crops]
    members = getattr(best, "estimators_", None)
    if members and hasattr(members[0], "feature_importances_"):
        stacked = np.mean([m.feature_importances_ for m in members
                           if hasattr(m, "feature_importances_")], axis=0)
        importances = sorted(
            ({"feature": f, "importance": round(float(v), 4)}
             for f, v in zip(feature_names, stacked)),
            key=lambda d: d["importance"], reverse=True)[:10]
    elif hasattr(best, "feature_importances_"):
        importances = sorted(
            ({"feature": f, "importance": round(float(v), 4)}
             for f, v in zip(feature_names, best.feature_importances_)),
            key=lambda d: d["importance"], reverse=True)[:10]

    bundle = {
        "model": best,
        "model_name": best_name,
        "task": "crop_suitability",
        "crops": crops,
        "district_features": DISTRICT_FEATURES,
        "districts": district_lookup(df),
        "metrics": metrics,
        "baselines": {
            "nearest_district": baseline_nn,
            "crop_frequency": baseline_freq,
            "positive_rate": positive_rate,
            "random_precision_at_3": random_precision,
        },
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "examples": int(X.shape[0]),
        "source": os.path.relpath(DATASET, BASE_DIR),
    }
    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(bundle, BUNDLE_PATH, compress=3)
    print(f"[train] saved {BUNDLE_PATH} "
          f"({os.path.getsize(BUNDLE_PATH) / 1e6:.1f} MB)")

    write_report(bundle, importances, args.quick, len(pairs))
    print(f"[train] wrote {REPORT_PATH}")
    return 0


def write_report(bundle: dict, importances, quick: bool,
                 pair_count: int) -> None:
    m = bundle["metrics"]
    b = bundle["baselines"]
    order = sorted(m, key=lambda n: m[n]["grouped_by_district"]
                   ["precision_at_3"], reverse=True)
    lines = [
        "# Crop recommendation model — district-trained",
        "",
        f"Trained {bundle['trained_at']} on `{bundle['source']}` "
        f"({bundle['examples']} examples from {len(bundle['districts'])} "
        f"districts, {pair_count} district-season pairs, "
        f"{len(bundle['crops'])} crops).",
        "",
        "## Task",
        "",
        "The source table lists, for each district and season, the crops grown",
        "there (5.4 on average). Every row of a district-season shares an",
        "identical feature vector, so 13-way single-label classification is",
        "unlearnable — it scores around 0.006, with identical inputs carrying",
        "different labels. The model is therefore trained as a suitability",
        "scorer: one example per (district, season, crop), labelled *does this",
        "district grow this crop in this season*. At inference it ranks the",
        "candidates the district layer already holds, giving a per-crop",
        "`ml_prob` that responds to soil, salinity, geography and climate.",
        "",
        "`area`, `production` and `yield` are excluded from the features: they",
        "are consequences of the crop being grown, not inputs to the choice.",
        "",
        "## Results",
        "",
        f"Top-{TOP_K} precision and recall, normalised by",
        f"`min({TOP_K}, crops the district grows)` so partial folds are",
        "comparable. With districts held out whole, that is ordinary",
        f"precision@{TOP_K}.",
        "",
        "| Model | Grouped P@3 | Grouped R@3 | Grouped AUC |"
        " Stratified P@3 | Stratified AUC |",
        "|---|---|---|---|---|---|",
    ]
    for name in order:
        g = m[name]["grouped_by_district"]
        s = m[name]["stratified"]
        lines.append(
            f"| {name} | {g['precision_at_3']:.3f} ± {g['precision_std']:.3f} "
            f"| {g['recall_at_3']:.3f} | {g['auc']:.3f} "
            f"| {s['precision_at_3']:.3f} | {s['auc']:.3f} |")
    lines += [
        "",
        "References on the same pairs:",
        "",
        f"- random ranking: P@3 {b['random_precision_at_3']:.3f}",
        f"- ranking by national crop frequency: "
        f"P@3 {b['crop_frequency']['precision_at_3']:.3f}",
        f"- the nearest known district's crop list: "
        f"P@3 {b['nearest_district']['precision_at_3']:.3f} "
        f"(R@3 {b['nearest_district']['recall_at_3']:.3f})",
        "",
        "**Grouped by district** holds out entire districts, so it measures",
        "generalisation to a district the model has never seen — the only case",
        "where a model can beat the app's existing district lookup.",
        "**Stratified** holds out rows from districts it has seen and mostly",
        "measures memorisation.",
        "",
        f"Selected: **{bundle['model_name']}**, by grouped precision@3.",
        "",
        "## Feature importance",
        "",
    ]
    if importances:
        for row in importances:
            lines.append(f"- `{row['feature']}` — {row['importance']:.4f}")
    else:
        lines.append("Not available for this model type.")
    lines += [
        "",
        "## How it is wired",
        "",
        "`district_data.py` loads `models/crop_model.pkl`. For each candidate",
        "crop it builds the district feature block plus that crop's one-hot",
        "column and takes the model's probability as the ML signal, alongside",
        "the district's historical yield/area, soil fit, climate fit and real",
        "price × yield return.",
        "",
        "If the bundle is absent — or the district is not in the lookup and no",
        "coordinates are available — the old seven-feature RandomForest is used",
        "instead, so `/predict` keeps working on a bare checkout.",
        "",
        f"Reproduce with `python train_crop_model.py"
        f"{' --quick' if quick else ''}`.",
        "",
    ]
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
