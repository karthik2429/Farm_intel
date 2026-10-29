# FarmIntel

Crop advisory + mandi prices + price forecasting for Indian farmers.
React 18 + TypeScript + Vite (frontend), FastAPI (backend).

## Run

```bash
./start.sh          # backend :8000 + frontend :8081
./start.sh stop     # stop both
./start.sh status
```

Backend venv at `collab/venv` (Python 3.14), frontend deps via `npm i`.

## Price pipeline (Phase 1 — real data only)

- **Ingest** — `Farm_intel/backend/mandi_ingest.py` fetches the AGMARKNET
  "Current Daily Price" snapshot from `api.data.gov.in` (key from
  `Farm_intel/.env: DATA_GOV_API_KEY`) and upserts it into the local SQLite
  store `backend/mandi_price_store.db`. The real 2024→2026 Goa historical
  parquet (`data/historical_prices/goa_merged/`) seeds the backfill.
- **Lookup** — `mandi_prices.get_price` serves: price store (real rows) →
  live AGMARKNET probe → MSP reference (flagged `is_real: false`).
  There is **no synthetic snapshot** anymore — responses report
  `source`, `date`, `badge`, `is_real`.
- **Forecast** — `price_forecast.py`: Holt-Winters (damped trend, weekly
  seasonality) over the accumulated daily history, rolling-origin
  backtest → MAPE, 80% CI from residuals, honest `stale_days` badge when
  history lags today. Scopes: market → district → state → India
  (≥60 observations per level).
- **API** — `POST /predict/14day`, `POST /predict/trajectory`,
  `GET /predict/single`, `GET /market/price`, `GET /market/status`,
  `GET /commodities`, `GET /markets` shape-match `src/lib/priceApi.ts` /
  `src/lib/marketApi.ts`.

### Daily history accrual

```bash
python backend/daily_ingest.py            # today's snapshot (local store)
python backend/daily_ingest.py --status   # coverage report
python backend/daily_ingest.py --goa      # + re-import Goa backfill
```

`.github/workflows/daily-mandi-ingest.yml` runs this daily in CI and
mirrors the newest rows into the shared Supabase table
(`supabase/migrations/20261029_mandi_prices.sql`) using the
`DATA_GOV_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` repo secrets.
Until the migration is applied on your Supabase project, CI runs keep to
each run's local store — apply it once via the Supabase SQL editor.

## Tests

```bash
./collab/venv/bin/python -m pytest Farm_intel/backend/tests -q
```

Guard tests fail if any synthetic price source ever returns, if MSP-only
responses claim `is_real: true`, or if forecasts degrade (inverted CI,
fabricated coverage).
