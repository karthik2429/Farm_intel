#!/bin/bash
# FarmIntel daily mandi ingest.
#
# api.data.gov.in refuses connections from datacenter networks - Railway and
# GitHub Actions both get ECONNREFUSED - so a network that can reach AGMARKNET
# has to fetch the daily snapshot and mirror it to Supabase, which the deployed
# API then reads.
#
# This script is location-independent: it uses the repo it lives in, so the
# scheduled copy under ~/FarmIntel-ingest works the same as the project copy.
# macOS blocks launchd/cron from reading ~/Desktop, which is why the schedule
# runs the clone (that one can also `git pull` to stay current).

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ingest-$(date +%Y-%m-%d).log"

# Best effort: a pull failure must never stop the day's ingest.
if [ "${FARMINTEL_SKIP_PULL:-0}" != "1" ] && [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" pull --ff-only --quiet origin main >/dev/null 2>&1 || true
fi

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

cd "$ROOT/backend" || exit 1

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') start ($ROOT)"

  "$PY" daily_ingest.py
  daily_status=$?
  echo "daily_ingest exit=$daily_status"

  # Derive this month's averages from the rows just written. It needs only
  # Supabase, so it still runs on a day the feed returns nothing.
  "$PY" refresh_monthly.py
  monthly_status=$?
  echo "refresh_monthly exit=$monthly_status"

  echo "=== $(date '+%Y-%m-%d %H:%M:%S') done"
  exit $(( daily_status != 0 || monthly_status != 0 ))
} >> "$LOG" 2>&1
