# Fertiliser recommendation model

Trained on `fertilizer_recommendation_dataset.csv` (3100 rows, 31 crops, 5 soil classes, 10 fertilisers).

## What changed

The endpoint answered by cosine similarity over the standardised
NPK/pH columns, comparing against every row of the same crop. It had
never been measured, and the soil class in the request was ignored
entirely even though the dataset is keyed by it.

This replaces it with a RandomForest over the columns the API can
actually supply: N, P, K, pH, soil class and crop.

## Results

| Method | Top-1 | Top-3 |
|---|---|---|
| Cosine retrieval (previous) | 0.561 | 0.766 |
| RandomForest (now) | 0.794 ± 0.008 | – |

RandomForest macro-F1: 0.727 across 10 fertiliser classes, which is the fairer number here: DAP is 1,054 of the 3,100 rows, so plain accuracy flatters a model that over-predicts it.

Both measured on the same rows; the retrieval figure is leave-one-out inside each crop, matching how the endpoint scoped it,
and the RandomForest figure is 5-fold cross-validation.

## Deliberate omission

The table also carries temperature, moisture, rainfall and carbon.
Feeding them in raises cross-validated accuracy to about 0.985, but
the fertiliser endpoint has no trustworthy version of them: the units
in this file are not the units the weather service returns, so any
mapping would be invented, and a confident wrong fertiliser is worse
than a hedged one. Accuracy is therefore reported as 0.81, not 0.98.

## How it is wired

`utils.recommend_fertilizer` uses the bundle when present, returning
the same `Fertilizer` / `Similarity` (now the model's probability) /
`Remark` shape the endpoint already returns; the cosine path remains
the fallback for a checkout without the bundle.

Reproduce with `python train_fertilizer_model.py`.
