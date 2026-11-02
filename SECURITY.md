# Security notes

## What is and isn't in this repository

- **No secret belongs in the frontend.** Every `VITE_` value ships inside the
  JavaScript bundle. The only Supabase values allowed there are the project URL
  and the **anon** (publishable) key — those are public by design and protected
  by Row Level Security.
- **Server-side secrets live only in `Farm_intel/.env`** (git-ignored) or in
  GitHub Actions secrets. They never reach `src/`, and the browser never sees
  them.
- All environment access goes through one module per side:
  `Farm_intel/backend/config.py` and `Farm_intel/src/lib/env.ts`. If you need a
  new variable, add it there and to the matching `.env*.example` file.

## Keys that were committed earlier and MUST be rotated

Earlier commits in this repository's history contained a `data.gov.in` API key
and Supabase project values in client code. Even though the current tree no
longer hardcodes them, **anything pushed to a remote must be treated as
compromised**:

1. **data.gov.in key** — sign in at <https://data.gov.in>, revoke the old key,
   generate a new one, put it in `Farm_intel/.env` as `DATA_GOV_API_KEY` and in
   the GitHub repository secret of the same name.
2. **Supabase anon key** — Project → Settings → API → *Rotate*. The anon key is
   public, but rotation is still recommended because the old value was pinned in
   a commit. Update `VITE_SUPABASE_ANON_KEY` and `.env`.
3. **Supabase service-role key** — if it was ever committed, rotate it
   immediately. It bypasses Row Level Security. It is only allowed in
   `Farm_intel/.env` and GitHub Actions secrets, never in `src/`.
4. **Any third-party key** (Gemini, Groq, OpenRouter, Bhashini, Sarvam,
   Unsplash, Pexels) that ever appeared in a commit: revoke and reissue.

Removing a file from the working tree does not remove it from history. If a
secret was pushed, rotation is the only real fix — `git filter-repo` is
optional cleanup, not a substitute.

## Deployment checklist

- [ ] `.env`, `.env.local`, `*.db`, `*.sqlite` are git-ignored (they are).
- [ ] `APP_ENV=production` in production so `/config/status` stops advertising
      setup links.
- [ ] Row Level Security is enabled on every user table and every policy is
      `auth.uid() = user_id`.
- [ ] The `soil-cards` Storage bucket is private, with per-user policies.
- [ ] `OPEN_EXTERNAL_ALLOWLIST` contains only government/extension domains.
- [ ] Rate limits are on for OTP requests and for `/chat`.
- [ ] The service-role key is used only by the daily ingest job.

## Reporting

This is a student/capstone project. Report issues to the repository owner.
