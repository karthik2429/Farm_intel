# Prediction audit — determinism, factor coverage, and the fixes

Date: **12 November 2026**. Backend `main:app` on `:8000`, React SPA on Vite `:5173`.

The question this audit answered: *is every prediction reproducible, and does the
crop recommendation actually use market price, profitability, soil and climate -
or does it only say it does?*

Short version: the numbers were already reproducible across all 22 endpoints, but
three things were wrong and one factor was missing:

1. the **soil factor ignored the farmer's soil test**;
2. the **price model silently sampled weather** for series without stored weather;
3. a **fabricated 84% confidence** appeared when the back-test could not run;
4. **profitability was revenue only**, with no input-cost term anywhere in the answer.

All four are fixed. Details below.

---

## 1. Determinism probe

Every endpoint was called three times with identical input and the JSON was
hashed and compared.

| Endpoint | Before | After |
|---|---|---|
| `POST /predict` | stable | stable |
| `POST /rotation/suggestions`, `/rotation/plan` | stable | stable |
| `POST /location/default-npk` | stable | stable |
| `GET /market/price`, `/market/history`, `/market/coverage` | stable | stable |
| `GET /weather` | stable | stable |
| `GET /crop/info`, `/commodities`, `/markets` | stable | stable |
| `POST /predict/14day`, `/predict/trajectory` | stable | stable |
| `GET /predict/single`, `/predict/factors` | stable | stable |
| `POST /fertilizer/recommend` | **varied** (`icar_advice` text) | stable |

Two sampling sources were found and removed even though the probe did not always
hit them:

- `price_predictor/goa_model/price_engine.py` synthesised monthly weather with
  `np.random.gamma/exponential/normal` **inside the request path**. Any series
  without stored weather returned a different forecast on every call. It is now a
  deterministic climatology (one value per month).
- `src/components/ui/sidebar.tsx` drew a skeleton width from `Math.random()`;
  it now derives the width from the element id.

The fertiliser advisory is prose from an LLM. It is now requested at
`temperature 0` and memoised on exactly the inputs that shape it (crop, soil, N,
P, K, pH, chosen fertilisers), so an identical question returns the identical
paragraph and costs one call. Failures (429, missing key) are **not** memoised, so
a retry can still succeed.

Regression tests: `backend/tests/test_determinism.py` (5 tests).

## 2. The soil factor was ignoring the soil test

`/predict` documented five inputs and scored `soil_fit` from the **district
survey** every time. A farmer who typed N 20 / P 10 / K 10 / pH 4.8 got the same
"soil match" as one who typed N 280 / P 90 / K 300 / pH 7.4, because the typed
values only reached the ML feature vector. The page then showed that repeated
number as the reason for the rank.

`district_data._score_candidates` now scores `_soil_fit(N, P, K, ph, ...)` with the
values the answer is actually based on - the farmer's test when supplied, the
district survey otherwise - and the endpoint keeps reporting the survey separately
in `soil_survey`, so the two are never confused.

Regression test: `test_user_supplied_soil_changes_the_answer`.

## 3. A fabricated confidence

`price_forecast.evaluate()` turned a missing back-test into `mape = 8.0`, and
`/predict/single` turned that into `confidence = 84%`. A number the platform had
never measured was presented as measured accuracy.

Now `mape` is `None` when the series was too short to back-test, `confidence` is
`None` with `confidence_basis = "not measured: too little history to back-test"`,
and only the *wording* falls back to a conservative error. Measured forecasts are
unchanged and now also state their basis, e.g. `rolling-origin back-test, MAPE 3.1%`.

## 4. Profitability is now an explicit, labelled factor

Ranking weights (district path, from `_score_candidates`):

| Factor | Weight | Source |
|---|---|---|
| District suitability model | 0.20 | `crop_model.pkl`, district-conditioned |
| District history (yield × area) | 0.18 | DES district crop map |
| Share of the district's cropped area | 0.14 | DES district crop map |
| Soil fit | 0.14 | farmer's soil test or DES soil survey |
| Climate fit | 0.09 | live Open-Meteo temperature and rainfall |
| Season fit | 0.05 | crop master (sowing window) |
| Agronomic prior | 0.05 | crop master |
| **Market return** | **0.15** | real mandi price × published yield band |
| Locality multiplier | ×0.55-1.00 | gates rare crops from the top slot |

Added in this audit: `fertiliser_cost_per_ha` and
`margin_after_fertiliser_per_ha`, computed from the ICAR dose (Appendix-A) at the
manual's own 2021 prices (Appendix-B), and shown on the crop detail page as
"Fertiliser cost per hectare" and "Margin after fertiliser".

Two deliberate limits, stated in the API and the UI:

- The margin **excludes** seed, labour, machinery, irrigation and transport, so it
  is labelled a margin after fertiliser, never profit. `cost_basis` travels with
  every figure and `excludes` lists what is missing.
- The ranking's market term stays on **gross return**, not margin: five app crops
  (cotton, sugarcane, turmeric, ginger, barley) have no ICAR dose row, so a
  margin-based score would compare a netted crop against a non-netted one and
  systematically favour the crops it knows least about.

## 5. What the probe and the tests now guarantee

- `backend/tests/test_determinism.py` - identical requests, identical payloads,
  across every scored endpoint.
- `backend/tests/test_crop_factors.py` - every alternative carries every factor;
  factors stay in range; `market_score` equals gross return / max gross return;
  `margin = gross - fertiliser cost`; a different soil test changes `soil_fit`; a
  different rainfall changes `climate_fit`; a different season changes the ranking.
- `backend/tests/test_fertilizer_dose.py` - the kg/ha layer matches the ICAR tables.

Whole suite: **311 passed, 2 xfailed** (the two xfails are the documented content
defects from `system-test-report.md`, unchanged).

## 6. Pages checked

All routes were loaded in the running app and inspected for render errors and
fabricated data: `/home`, `/market`, `/predict`, `/crops`, `/crop-detail`,
`/rotation`, `/fertilizer`, `/chat`, `/profile`, `/design`, 404. No page held mock
data, and no page showed a number without its source: prices carry a
live/cached/monthly/MSP badge, forecasts carry their series basis and staleness,
and missing values render `--` rather than a default.

Reproduce the UI checks:

```bash
cd Farm_intel && npm run dev            # :5173
./.venv/bin/python -m uvicorn main:app --port 8000 --app-dir backend
```

Reproduce the tests:

```bash
cd Farm_intel/backend
../.venv/bin/python -m pytest tests/test_determinism.py tests/test_crop_factors.py -q
```
