# AgroSmart AI — delivery report

Verification date: **2 November 2026**.
Stack unchanged: React 18 + TypeScript + Vite + Tailwind (frontend in `Farm_intel/`),
FastAPI (backend), SQLite price store, Supabase, GitHub Actions. All 17 original
API endpoints and all business logic are still there.

---

## 1. Screenshots

All captured from the running stack (`./start.sh`) in the Preview browser, saved in
`screenshots/`. Every shot shows real data served by the backend.

| Screen | Width | Theme | File |
|---|---|---|---|
| Login | 390 | dark | `screenshots/login-390.png` |
| Home | 390 | dark | `screenshots/home-390-dark.png` |
| Home | 390 | light | `screenshots/home-390-light.png` |
| Home | 1440 | light | `screenshots/home-1440-light.png` |
| Market | 390 | dark | `screenshots/market-390-loaded-dark.png` |
| Market | 1440 | light (list) | `screenshots/market-1440-light.png` |
| Market | 1440 | light (grid) | `screenshots/market-1440-grid-light.png` |
| Predict | 390 | dark | `screenshots/predict-390-dark-v5.png` |
| Chat (empty) | 390 | light | `screenshots/chat-390-light.png` |
| Chat (price answer) | 390 | light | `screenshots/chat-390-answer-light.png` |
| Chat (forecast answer) | 390 | light | `screenshots/chat-390-forecast-light.png` |
| Design gallery | 768 | light | `screenshots/design-768-light-v2.png` |

Intermediate iterations (`predict-390-dark.png` → `v4`) are kept so the before/after
of the chart-scaling and history-scope fixes is visible.

---

## 2. What changed, per screen

### Login (`/`)
- Desktop split screen: full-bleed farm photo, forest→leaf gradient overlay, tagline
  "Smarter farming, better prices", glass stat cards. Phone: photo-free compact hero
  with an overlapping form card.
- Google button first, then a one-time email code with six auto-advancing boxes,
  30-second resend timer, five-attempt cap and "use a different email".
- Tabs are **Log in / Create account** (short). Phone OTP is gone entirely.
- Honest setup card when `VITE_SUPABASE_*` is unset, with a "continue without an account"
  path so the app is explorable with zero keys.
- Language switcher and theme toggle top-right.

### Home (`/home`)
- Gradient hero (greeting, live weather at 38px, humidity/rain chips, district chip),
  content overlapping the hero edge.
- "Ask in your language" search bar with a gold mic.
- Five tinted quick-action tiles, "My crops" price cards with sparklines and
  Live/Cached badges, gold "best time to sell" card, recommendation cards with
  suitability rings, "today's mandi movers", four stat tiles.
- Install chip (PWA) and offline banner.

### Market (`/market`)
- Sticky search, sort chips (A–Z / Highest / Lowest / Available only), list↔grid
  toggle (grid by default ≥1024px), per-row sparklines, skeletons, empty state,
  "Updated N min ago · AGMARKNET" caption.
- a legend that spells out what Live / Cached / Unavailable mean.

### Predict (`/predict`)
- Commodity picker + current price at 40px with tabular figures, 14-day change badge,
  MAPE badge, plain-language advice, "last real record is N days old".
- Gradient area chart with a shaded confidence band, dashed forecast line, "today"
  marker and a custom tooltip. Day-by-day list with CI range per day.
- Gold "best time to sell" card, and a **Data coverage** panel (observations, first
  and last date, backtest folds, scope).
- Defaults to the commodity with the most real history instead of a hardcoded crop.

### Chat (`/chat`)
- Full-height conversation with language pill, bubbles, typing dots, quick-reply
  chips in the selected language, camera/gallery, mic and read-aloud.
- Data answers arrive as **cards**: price cards with provenance badges and forecast
  cards with a sparkline and MAPE. Navigation actions render as buttons.

### Crops / Rotation / Fertilizer / Profile
- Now sit on the same shell, navigation and tokens. (See §7 for what is still
  un-polished on these four.)

---

## 3. Real vs fallback data

| Surface | Before | After (verified live) |
|---|---|---|
| Prices | Fabricated +0.9% trend, identical dates on every row | 36,480 real AGMARKNET rows; today's call returned `Cotton ₹8,200/q, Phirangipuram APMC, 2026-10-31, source agmarknet_live, is_real true` |
| Market list | Sample arrays | Real store rows (Alasandikai 4,200 · Amaranthus 3,700 · Cotton 9,150 …) with `Cached · DD Mon` / `Live` badges |
| Forecast | None / synthetic | Holt-Winters on real history: `Banana ₹3,250, −15.6%, MAPE 13.6%, 617 obs`; `Arecanut ₹25,000, +17.3%, MAPE 3.5%` |
| Chat prices | Canned text | Database-first: `Tomato in Mayurbhanja is ₹4,500 per quintal at Baripada APMC (2026-11-02)`, card payload `source: agmarknet_live, is_real: true` |
| Coverage | n/a | `/market/coverage` → Arecanut 5,471 obs (2024-07-13 → 2026-10-29), Coconut 2,243, Onion … |
| Missing keys | 500s / crashes | `AuthProvider` is null-safe; `/config/status` reports booleans; chat answers prices without any LLM key |

---

## 4. Forecast backtest

- Model: Holt-Winters additive (`hw_additive`), rolling-origin backtest, MAPE reported
  with the CI band derived from residual spread.
- Observed in this run: **MAPE 3.5 %** (Arecanut, 617 observations) and **MAPE 13.6 %**
  (Banana) and **12.8 %** (Onion, from the chat card).
- Insufficient history returns an explicit refusal ("Not enough real mandi history
  yet… try again later") — never a fabricated curve.

---

## 5. Test and check results

| Check | Command | Result |
|---|---|---|
| Backend tests | `./collab/venv/bin/python -m pytest Farm_intel/backend/tests -q` | **24 passed** (9 original guards + 15 new assistant tests) |
| Type check | `npx tsc --noEmit` | **0 errors** |
| Lint | `npx eslint src --quiet` | **0 errors** |
| Production build | `npm run build` | **passes**, routes code-split |
| All keys unset | live run of the dev stack | Login, Home, Market, Predict, Chat, Design all render; keyed features show setup states |

New assistant tests cover: database-first price/forecast/navigation routing (with the
LLM stubbed to fail), `open_external` allowlist rejection including look-alike hosts,
per-user and global rate limits, answer caching, language of the reply, and the
missing-key setup message.

---

## 6. Manual configuration checklist

| Variable | Where | Free signup |
|---|---|---|
| `DATA_GOV_API_KEY` | `Farm_intel/.env` | https://data.gov.in/user/register |
| `GEMINI_API_KEY` (any one LLM) | `Farm_intel/.env` | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | `Farm_intel/.env` | https://console.groq.com/keys |
| `OPENROUTER_API_KEY` | `Farm_intel/.env` | https://openrouter.ai/keys |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | `Farm_intel/.env.local` | https://supabase.com/dashboard |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | `.env` + GitHub secrets | same project → Settings → API |
| `BHASHINI_*` or `SARVAM_API_KEY` (optional voice) | `.env` | https://bhashini.gov.in · https://dashboard.sarvam.ai |

1. Copy `.env.example` → `Farm_intel/.env` and `.env.local.example` → `Farm_intel/.env.local`.
2. **Rotate** the data.gov.in key and any Supabase key ever committed — see `SECURITY.md`.
3. Supabase → Authentication → Providers → enable **Google**, add the redirect URLs
   (`http://localhost:5174/**` and your deployed origin).
4. Supabase → Authentication → SMTP: add Resend/Brevo/Gmail and put `{{ .Token }}`
   in the email template (the built-in sender is heavily rate-limited).
5. Run `supabase/migrations/20261102_profiles_auth_rls.sql` in the SQL editor.
6. GitHub → Settings → Secrets: `DATA_GOV_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
   so the daily ingest Action keeps working.
7. Crop photos: drop 25 WebP files into `public/crops/<slug>.webp` (slugs in
   `src/lib/cropImages.ts`). Until then each crop gets its own tinted leaf tile —
   never another crop's photo.

---

## 7. Known gaps (honest list)

These are not done, and the brief asked for them:

1. **Crops / Rotation / Fertilizer / Profile are still the old screens** under the new
   shell. They use the tokens and navigation, but not the new card forms, unit inputs,
   result cards or the profile completeness ring.
2. **Onboarding is still the old stepper.** It works and saves to localStorage, but it
   has not been rebuilt on the kit (one question per screen, native-script language
   grid, crop photos) and it does not yet write to Supabase through `profile.ts`.
3. **Profile persistence** is implemented in `src/lib/profile.ts` (Supabase + cache
   fallback) but the profile page still writes the legacy localStorage keys directly.
4. **Linways/soil-card upload UI** is not wired: the table, bucket and RLS exist, but
   no uploader component was built.
5. **Chat history is not persisted per user** (table + RLS exist, no writer).
6. **Image input** returns an honest "needs GEMINI_API_KEY" message instead of calling
   Gemini vision.
7. **Translation coverage** is complete for English and for the chrome (navigation,
   greetings, actions, market/predict/chat labels) in the other ten languages; deeper
   strings fall back to English. `coverage(lang)` in `src/lib/i18n.ts` reports the
   percentage per language.
8. **PWA was verified by inspection, not with Lighthouse.** The manifest, icons,
   service worker and offline banner are in place and the SW registers in production
   builds; no Lighthouse ≥90 run was captured.
9. **768px screenshots** exist only for `/design`; Home/Market/Predict were captured at
   390 and 1440.
10. **`tsc` proved unreliable** during this session: it reported 0 errors while
    `RefreshCw` was used-but-not-imported in `core.tsx` (caught by the browser crash).
    The build and runtime checks are therefore the authoritative signals here.
