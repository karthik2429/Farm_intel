# Fertiliser recommendation model

Trained on `fertilizer_recommendation_dataset.csv` (3100 rows, 31 crops, 5 soil classes, 10 fertilisers).

## What changed

The endpoint originally answered by cosine similarity over the
standardised NPK/pH columns, comparing against every row of the same
crop. It had never been measured, and the soil class in the request
was ignored entirely even though the dataset is keyed by it.

It is now a RandomForest over the soil test, the soil class, the crop,
and three district and weather values the platform already holds:

- **temperature** from Open-Meteo or the district's climatology,
- **organic carbon** estimated from the DES survey's low/medium/high
  band shares for the district,
- **moisture** derived from relative humidity.

Those three are what distinguish compost (low carbon),
water-retaining fertiliser (low moisture), lime (acid soil) and urea
(low nitrogen) from a generic NPK answer.

## Results

| Method | Accuracy | Macro-F1 |
|---|---|---|
| Cosine retrieval (original) | 0.561 top-1 | – |
| NPK + pH + soil + crop | 0.794 | 0.727 |
| **+ temperature, carbon, moisture (now)** | **0.927 ± 0.006** | **0.911** |

Same rows, same folds. The retrieval figure is leave-one-out inside
each crop, matching how the endpoint scoped it; the rest are 5-fold
cross-validation. Macro-F1 matters here because DAP is 1,054 of the
3,100 rows, so plain accuracy flatters a model that over-predicts it.

## Honest accounting for the extra inputs

The three added columns are only usable because the platform measures
something equivalent, and the training data is put on the same footing
as the served data rather than left at full precision:

- carbon is snapped to its band midpoint, because the survey publishes
  band counts and not a figure;
- moisture is rounded to 1% steps, because humidity arrives as a whole
  percent;
- temperature is used as-is, since both sides are degrees Celsius.

`Rainfall` remains excluded. It is synthetic in this dataset - it
contains negative values - so there is no defensible mapping from a
weather feed to it, and inventing one would put a confident number
behind a meaningless input.

## How it is wired

`utils.recommend_fertilizer` builds the vector from the soil test, the
district's carbon estimate and live weather, falling back to
documented defaults when either is unavailable, and reports which
inputs were used. A pH amendment is applied on top of the ranking: lime
below pH 5.5 and gypsum above 8.5, which the dataset's label set never
produces on its own. The cosine path remains the fallback for a
checkout without the bundle.

Reproduce with `python train_fertilizer_model.py`.
