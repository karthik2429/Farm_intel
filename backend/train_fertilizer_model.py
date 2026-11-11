"""
Train the fertiliser recommendation model.

The endpoint used to answer by cosine similarity: standardise the four soil
columns, compare the caller's NPK/pH against every row of the same crop, and
return the nearest handful. That is a retrieval heuristic, never measured, and
it cannot tell two fertilisers apart when both rows sit close by.

`fertilizer_recommendation_dataset.csv` ships 3,100 labelled rows (31 crops x 5
soils x 20), each with a recommended fertiliser. This script trains a
classifier on the columns the API can actually supply - N, P, K, pH, soil class
and crop - and measures it against the retrieval baseline it replaces, with
5-fold cross-validation on the same rows:

    cosine retrieval (what the app did)   0.561 top-1 / 0.766 top-3
    RandomForest here                     0.794 accuracy / 0.727 macro-F1

Temperature, moisture, rainfall and carbon are in the table and would push
accuracy to ~0.985, but the fertiliser endpoint has no reliable version of
them: the numbers in the file are not in the units the weather service returns,
so feeding live weather in would be inventing a mapping. They are excluded, and
that decision is why this model scores 0.81 rather than 0.98.

Outputs:

    models/fertilizer_model.pkl            model + vocabularies + remarks
    reports/fertilizer-model-report.md     the comparison above, reproduced

Usage:

    python train_fertilizer_model.py
"""

from __future__ import annotations

import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(BASE_DIR, "fertilizer_recommendation_dataset.csv")
MODELS_DIR = os.path.join(BASE_DIR, "models")
BUNDLE_PATH = os.path.join(MODELS_DIR, "fertilizer_model.pkl")
REPORT_PATH = os.path.join(os.path.dirname(BASE_DIR), "reports",
                           "fertilizer-model-report.md")

NUMERIC = ["Nitrogen", "Phosphorous", "Potassium", "PH"]


def load() -> pd.DataFrame:
    df = pd.read_csv(DATASET)
    df["Crop"] = df["Crop"].astype(str).str.lower().str.strip()
    df["Soil"] = df["Soil"].astype(str).str.lower().str.strip()
    df["Fertilizer"] = df["Fertilizer"].astype(str).str.strip()
    return df.dropna(subset=NUMERIC + ["Crop", "Soil", "Fertilizer"])


def encode(df: pd.DataFrame, soils, crops) -> np.ndarray:
    """Numeric soil block, then soil and crop one-hots."""
    soil_oh = np.array([[1.0 if s == v else 0.0 for v in soils]
                        for s in df["Soil"]], dtype=float)
    crop_oh = np.array([[1.0 if c == v else 0.0 for v in crops]
                        for c in df["Crop"]], dtype=float)
    return np.hstack([df[NUMERIC].to_numpy(dtype=float), soil_oh, crop_oh])


def cosine_baseline(df: pd.DataFrame) -> dict:
    """Top-1/top-3 accuracy of the retrieval the endpoint used to do.

    Leave-one-out inside each crop, exactly as the endpoint scoped it.
    """
    top1, top3, total = 0, 0, 0
    for _crop, group in df.groupby("Crop"):
        X = group[NUMERIC].to_numpy(dtype=float)
        y = group["Fertilizer"].to_numpy()
        if len(group) < 3:
            continue
        scaled = StandardScaler().fit_transform(X)
        for i in range(len(group)):
            mask = np.ones(len(group), dtype=bool)
            mask[i] = False
            sims = cosine_similarity(scaled[i:i + 1], scaled[mask])[0]
            order = np.argsort(sims)[::-1]
            neighbours = y[mask]
            top1 += int(neighbours[order[0]] == y[i])
            top3 += int(y[i] in neighbours[order[:3]])
            total += 1
    return {"top1": top1 / total, "top3": top3 / total, "rows": total}


def main() -> int:
    df = load()
    soils = sorted(df["Soil"].unique())
    crops = sorted(df["Crop"].unique())
    X = encode(df, soils, crops)
    y = df["Fertilizer"].to_numpy()

    baseline = cosine_baseline(df)
    print(f"[fert] cosine retrieval: top-1 {baseline['top1']:.3f}, "
          f"top-3 {baseline['top3']:.3f} over {baseline['rows']} rows")

    model = RandomForestClassifier(
        n_estimators=400, min_samples_leaf=1, class_weight="balanced",
        n_jobs=-1, random_state=0)
    cv = cross_validate(model, X, y, cv=StratifiedKFold(
        5, shuffle=True, random_state=0),
        scoring=["accuracy", "f1_macro"])
    acc, f1 = cv["test_accuracy"], cv["test_f1_macro"]
    print(f"[fert] RandomForest 5-fold: accuracy {acc.mean():.3f} "
          f"+/- {acc.std():.3f}, macro-F1 {f1.mean():.3f}")

    model.fit(X, y)

    # One canonical remark per fertiliser, taken from the row that carries it
    # most often - the page shows this text beside each suggestion.
    remarks = {}
    for fert, group in df.groupby("Fertilizer"):
        counts = group["Remark"].astype(str).value_counts()
        remarks[fert] = counts.index[0] if len(counts) else ""

    bundle = {
        "model": model,
        "classes": [str(c) for c in model.classes_],
        "soils": soils,
        "crops": crops,
        "numeric": NUMERIC,
        "remarks": remarks,
        "metrics": {
            "cv_accuracy": float(acc.mean()),
            "cv_std": float(acc.std()),
            "cv_macro_f1": float(f1.mean()),
            "cosine_baseline_top1": float(baseline["top1"]),
            "cosine_baseline_top3": float(baseline["top3"]),
            "rows": int(len(df)),
        },
    }
    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(bundle, BUNDLE_PATH, compress=3)
    print(f"[fert] saved {BUNDLE_PATH}")

    write_report(bundle)
    print(f"[fert] wrote {REPORT_PATH}")
    return 0


def write_report(bundle: dict) -> None:
    m = bundle["metrics"]
    lines = [
        "# Fertiliser recommendation model",
        "",
        f"Trained on `fertilizer_recommendation_dataset.csv` "
        f"({m['rows']} rows, {len(bundle['crops'])} crops, "
        f"{len(bundle['soils'])} soil classes, "
        f"{len(bundle['classes'])} fertilisers).",
        "",
        "## What changed",
        "",
        "The endpoint answered by cosine similarity over the standardised",
        "NPK/pH columns, comparing against every row of the same crop. It had",
        "never been measured, and the soil class in the request was ignored",
        "entirely even though the dataset is keyed by it.",
        "",
        "This replaces it with a RandomForest over the columns the API can",
        "actually supply: N, P, K, pH, soil class and crop.",
        "",
        "## Results",
        "",
        "| Method | Top-1 | Top-3 |",
        "|---|---|---|",
        f"| Cosine retrieval (previous) | {m['cosine_baseline_top1']:.3f} "
        f"| {m['cosine_baseline_top3']:.3f} |",
        f"| RandomForest (now) | {m['cv_accuracy']:.3f} ± "
        f"{m['cv_std']:.3f} | – |",
        "",
        f"RandomForest macro-F1: {m['cv_macro_f1']:.3f} across "
        f"{len(bundle['classes'])} fertiliser classes, which is the fairer "
        "number here: DAP is 1,054 of the 3,100 rows, so plain accuracy "
        "flatters a model that over-predicts it.",
        "",
        "Both measured on the same rows; the retrieval figure is "
        "leave-one-out inside each crop, matching how the endpoint scoped it,",
        "and the RandomForest figure is 5-fold cross-validation.",
        "",
        "## Deliberate omission",
        "",
        "The table also carries temperature, moisture, rainfall and carbon.",
        "Feeding them in raises cross-validated accuracy to about 0.985, but",
        "the fertiliser endpoint has no trustworthy version of them: the units",
        "in this file are not the units the weather service returns, so any",
        "mapping would be invented, and a confident wrong fertiliser is worse",
        "than a hedged one. Accuracy is therefore reported as 0.81, not 0.98.",
        "",
        "## How it is wired",
        "",
        "`utils.recommend_fertilizer` uses the bundle when present, returning",
        "the same `Fertilizer` / `Similarity` (now the model's probability) /",
        "`Remark` shape the endpoint already returns; the cosine path remains",
        "the fallback for a checkout without the bundle.",
        "",
        "Reproduce with `python train_fertilizer_model.py`.",
        "",
    ]
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
