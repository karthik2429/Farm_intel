# Crop recommendation model — district-trained

Trained 2026-11-11T19:23:33+00:00 on `hybrid_crop_model/datasets/final_training_dataset.csv` (9217 examples from 355 districts, 709 district-season pairs, 13 crops).

## Task

The source table lists, for each district and season, the crops grown
there (5.4 on average). Every row of a district-season shares an
identical feature vector, so 13-way single-label classification is
unlearnable — it scores around 0.006, with identical inputs carrying
different labels. The model is therefore trained as a suitability
scorer: one example per (district, season, crop), labelled *does this
district grow this crop in this season*. At inference it ranks the
candidates the district layer already holds, giving a per-crop
`ml_prob` that responds to soil, salinity, geography and climate.

`area`, `production` and `yield` are excluded from the features: they
are consequences of the crop being grown, not inputs to the choice.

## Results

Top-3 precision and recall, normalised by
`min(3, crops the district grows)` so partial folds are
comparable. With districts held out whole, that is ordinary
precision@3.

| Model | Grouped P@3 | Grouped R@3 | Grouped AUC | Stratified P@3 | Stratified AUC |
|---|---|---|---|---|---|
| Ensemble | 0.958 ± 0.010 | 0.582 | 0.974 | 0.998 | 0.979 |
| XGBoost | 0.957 ± 0.009 | 0.581 | 0.974 | 0.998 | 0.980 |
| RandomForest | 0.954 ± 0.011 | 0.579 | 0.969 | 0.997 | 0.971 |

References on the same pairs:

- random ranking: P@3 0.421
- ranking by national crop frequency: P@3 0.683
- the nearest known district's crop list: P@3 0.897 (R@3 0.538)

**Grouped by district** holds out entire districts, so it measures
generalisation to a district the model has never seen — the only case
where a model can beat the app's existing district lookup.
**Stratified** holds out rows from districts it has seen and mostly
measures memorisation.

Selected: **Ensemble**, by grouped precision@3.

## Feature importance

- `crop_maize` — 0.1210
- `crop_gram` — 0.0958
- `crop_wheat` — 0.0953
- `crop_lentil` — 0.0698
- `crop_barley` — 0.0627
- `season_rabi` — 0.0573
- `temp` — 0.0503
- `humidity` — 0.0451
- `rainfall` — 0.0415
- `crop_tur` — 0.0415

## How it is wired

`district_data.py` loads `models/crop_model.pkl`. For each candidate
crop it builds the district feature block plus that crop's one-hot
column and takes the model's probability as the ML signal, alongside
the district's historical yield/area, soil fit, climate fit and real
price × yield return.

If the bundle is absent — or the district is not in the lookup and no
coordinates are available — the old seven-feature RandomForest is used
instead, so `/predict` keeps working on a bare checkout.

Reproduce with `python train_crop_model.py`.
