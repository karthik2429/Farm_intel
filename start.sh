#!/usr/bin/env bash
# =============================================================================
# FarmIntel / FarmIntel — one-command dev stack
#
#   ./start.sh            start backend + frontend, print the URLs
#   ./start.sh stop       stop both (only processes this script started)
#   ./start.sh status     show what is running
#   ./start.sh backend    start only the API
#   ./start.sh frontend   start only the web app
#
# Ports come from the environment first, then Farm_intel/.env:
#   BACKEND_PORT (default 8000) and FRONTEND_PORT (default 5173).
# Occupied ports are never killed: the script picks the next free one and
# tells you. PIDs are tracked in .run/ so `stop` only stops our own servers.
# =============================================================================
set -uo pipefail

# Works from either layout: a plain clone (this folder is the repo root) or a
# larger checkout where Farm_intel/ sits one level down.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/package.json" ]; then
  FRONTEND_DIR="$SCRIPT_DIR"
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  ROOT="$SCRIPT_DIR"
  FRONTEND_DIR="$ROOT/Farm_intel"
fi
BACKEND_DIR="$FRONTEND_DIR/backend"

# Python for the API: $VENV_PY, else the shared/legacy venv, else a local one,
# else the system interpreter.
if [ -z "${VENV_PY:-}" ]; then
  for cand in "$ROOT/collab/venv/bin/python" \
              "$FRONTEND_DIR/.venv/bin/python" \
              "$FRONTEND_DIR/backend/.venv/bin/python"; do
    if [ -x "$cand" ]; then VENV_PY="$cand"; break; fi
  done
  [ -z "${VENV_PY:-}" ] && VENV_PY="python3"
fi
RUN_DIR="$ROOT/.run"
BACKEND_LOG="/tmp/farmintel_backend.log"
FRONTEND_LOG="/tmp/farmintel_frontend.log"

mkdir -p "$RUN_DIR"

# ---- config -----------------------------------------------------------------
env_value() {  # env_value KEY default  -> real env wins over .env
  local key="$1" fallback="$2" found=""
  if [ -f "$FRONTEND_DIR/.env" ]; then
    found="$(grep -E "^${key}=" "$FRONTEND_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | xargs || true)"
  fi
  if [ -n "${!key:-}" ]; then
    echo "${!key}"
  elif [ -n "$found" ]; then
    echo "$found"
  else
    echo "$fallback"
  fi
}

BACKEND_PORT="$(env_value BACKEND_PORT 8000)"
FRONTEND_PORT="$(env_value FRONTEND_PORT 5173)"

# ---- port helpers -----------------------------------------------------------
port_in_use() { lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

next_free_port() {  # next_free_port START
  local p="$1" tries=0
  while port_in_use "$p"; do
    p=$((p + 1)); tries=$((tries + 1))
    [ "$tries" -gt 40 ] && { echo ""; return; }
  done
  echo "$p"
}

pid_file() { echo "$RUN_DIR/$1.pid"; }

read_pid() {  # read_pid name -> pid if that process is still ours
  local f; f="$(pid_file "$1")"
  [ -f "$f" ] || return 1
  local pid; pid="$(cat "$f" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && { echo "$pid"; return 0; }
  rm -f "$f"
  return 1
}

# ---- backend ----------------------------------------------------------------
start_backend() {
  local pid
  if pid="$(read_pid backend)"; then
    echo "✅ Backend already running (pid $pid) → http://127.0.0.1:$BACKEND_PORT"
    return 0
  fi
  if port_in_use "$BACKEND_PORT"; then
    local chosen; chosen="$(next_free_port "$BACKEND_PORT")"
    echo "⚠️  Port $BACKEND_PORT is used by another program (not touching it)."
    if [ -z "$chosen" ]; then echo "❌ No free port found for the backend."; return 1; fi
    echo "   Using $chosen instead."
    BACKEND_PORT="$chosen"
  fi
  if [ ! -x "$VENV_PY" ]; then
    echo "❌ Python venv not found at $VENV_PY"
    echo "   Create it once: python3 -m venv collab/venv && collab/venv/bin/pip install -r Farm_intel/backend/requirements.txt"
    return 1
  fi
  echo "Starting backend on :$BACKEND_PORT …"
  (
    cd "$BACKEND_DIR" || exit 1
    BACKEND_PORT="$BACKEND_PORT" nohup "$VENV_PY" serve.py >>"$BACKEND_LOG" 2>&1 &
    echo $! > "$(pid_file backend)"
  )
  for _ in $(seq 1 45); do
    if curl -fsS -m 2 "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
      echo "✅ Backend ready → http://127.0.0.1:$BACKEND_PORT"
      return 0
    fi
    sleep 1
  done
  echo "❌ Backend did not answer on :$BACKEND_PORT — see $BACKEND_LOG"
  return 1
}

# ---- frontend ---------------------------------------------------------------
start_frontend() {
  local pid
  if pid="$(read_pid frontend)"; then
    echo "✅ Frontend already running (pid $pid) → http://localhost:$FRONTEND_PORT"
    return 0
  fi
  if port_in_use "$FRONTEND_PORT"; then
    local chosen; chosen="$(next_free_port "$FRONTEND_PORT")"
    echo "⚠️  Port $FRONTEND_PORT is used by another program (not touching it)."
    if [ -z "$chosen" ]; then echo "❌ No free port found for the frontend."; return 1; fi
    echo "   Using $chosen instead."
    FRONTEND_PORT="$chosen"
  fi
  echo "Starting frontend on :$FRONTEND_PORT …"
  (
    cd "$FRONTEND_DIR" || exit 1
    VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://127.0.0.1:$BACKEND_PORT}" \
      nohup npm run dev -- --port "$FRONTEND_PORT" --strictPort \
      >>"$FRONTEND_LOG" 2>&1 &
    echo $! > "$(pid_file frontend)"
  )
  for _ in $(seq 1 45); do
    if curl -fsS -m 2 "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1; then
      echo "✅ Frontend ready → http://localhost:$FRONTEND_PORT"
      return 0
    fi
    sleep 1
  done
  echo "❌ Frontend did not answer on :$FRONTEND_PORT — see $FRONTEND_LOG"
  return 1
}

# ---- actions ----------------------------------------------------------------
stop_one() {
  local name="$1" pid
  if pid="$(read_pid "$name")"; then
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    rm -f "$(pid_file "$name")"
    echo "🛑 $name stopped (pid $pid)"
  else
    echo "$name is not running (nothing started by this script)"
  fi
}

status_one() {
  local name="$1" port="$2" pid
  if pid="$(read_pid "$name")"; then
    echo "  $name  UP    :$port  (pid $pid)"
  else
    echo "  $name  DOWN  :$port"
  fi
}

do_start() {
  start_backend
  start_frontend
  echo
  echo "──────────────────────────────────────────────"
  echo "  API   http://127.0.0.1:$BACKEND_PORT"
  echo "  App   http://localhost:$FRONTEND_PORT"
  echo "  Logs  $BACKEND_LOG / $FRONTEND_LOG"
  echo "──────────────────────────────────────────────"
}

case "${1:-start}" in
  start)    do_start ;;
  backend)  start_backend ;;
  frontend) start_frontend ;;
  stop)
    stop_one frontend
    stop_one backend
    ;;
  status)
    echo "FarmIntel dev stack:"
    status_one backend "$BACKEND_PORT"
    status_one frontend "$FRONTEND_PORT"
    echo "  API   http://127.0.0.1:$BACKEND_PORT/config/status"
    echo "  App   http://localhost:$FRONTEND_PORT"
    ;;
  *)
    echo "Usage: ./start.sh [start|stop|status|backend|frontend]"
    exit 1
    ;;
esac
