#!/usr/bin/env bash
# Local development launcher: ngrok tunnel + FastAPI backend (:8000) + Next.js frontend (:3000).
#
#   ./scripts/dev.sh            start everything (re-runnable: stops previous instances first)
#   ./scripts/dev.sh --no-ngrok start without a tunnel (no outbound calls will reach Twilio webhooks)
#
# The ngrok https URL is exported as PUBLIC_BASE_URL / TWILIO_PUBLIC_BASE_URL so the backend
# builds Twilio webhook + media-stream URLs that Twilio can reach. Real environment variables
# override the values in .env, so .env itself is never rewritten.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/venv"
UV="${UV:-$HOME/.local/bin/uv}"
USE_NGROK=1
[ "${1:-}" = "--no-ngrok" ] && USE_NGROK=0

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT

if [ ! -f "$ROOT/.env" ]; then
  echo "✖ $ROOT/.env is missing — copy .env.example to .env and fill in the keys."
  exit 1
fi

# --- Stop leftovers from a previous run so a plain re-run always works ------------------------
# Wait for a TCP port to be released; anything still bound after the grace period is SIGKILLed.
# (A uvicorn worker hung in startup ignores SIGTERM, and its --reload supervisor then keeps the
#  port forever — the "[Errno 98] Address already in use" on re-run.)
free_port() {
  local port="$1"
  for _ in $(seq 1 20); do
    fuser -s "$port/tcp" 2>/dev/null || return 0
    sleep 0.5
  done
  echo "▶ Port $port still busy — force-killing the old process."
  fuser -k -KILL "$port/tcp" >/dev/null 2>&1 || true
  sleep 1
}
pkill -f "$VENV/bin/uvicorn app.main" 2>/dev/null || true
pkill -f "ngrok http 8000" 2>/dev/null || true
pkill -f "$FRONTEND/node_modules/.bin/next" 2>/dev/null || true
free_port 8000
free_port 3000

# --- Backend virtualenv (system python has no venv module; uv is the supported way) ------------
if [ ! -x "$VENV/bin/python" ]; then
  echo "▶ Creating backend venv with uv..."
  if [ -x "$UV" ]; then
    "$UV" venv -q "$VENV" --python 3.12
  else
    python3 -m venv "$VENV"
  fi
fi
if ! "$VENV/bin/python" -c "import fastapi, sqlalchemy, httpx, websockets, cryptography" >/dev/null 2>&1; then
  echo "▶ Installing backend requirements..."
  if [ -x "$UV" ]; then
    "$UV" pip install -q --python "$VENV/bin/python" -r "$BACKEND/requirements-dev.txt"
  else
    "$VENV/bin/pip" install -q -r "$BACKEND/requirements-dev.txt"
  fi
fi
if [ ! -x "$VENV/bin/uvicorn" ]; then
  echo "✖ uvicorn missing in $VENV — reinstall requirements (rm -rf backend/venv and re-run)."
  exit 1
fi

# --- Frontend dependencies -------------------------------------------------------------------
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "▶ Installing frontend dependencies..."
  (cd "$FRONTEND" && npm install)
fi

# --- ngrok tunnel ------------------------------------------------------------------------------
PUBLIC_BASE_URL=""
if [ "$USE_NGROK" -eq 1 ]; then
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "✖ ngrok not found in PATH (install it or run with --no-ngrok)."
    exit 1
  fi
  echo "▶ Starting ngrok tunnel to port 8000..."
  ngrok http 8000 --log=stdout > /tmp/banglabot-ngrok.log 2>&1 &
  for _ in $(seq 1 25); do
    PUBLIC_BASE_URL=$(curl -sf --max-time 2 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
      | python3 -c 'import json,sys
try:
    tunnels = json.load(sys.stdin).get("tunnels") or []
    print(next(t["public_url"] for t in tunnels if str(t.get("public_url", "")).startswith("https")))
except Exception:
    sys.exit(1)
' 2>/dev/null) && [ -n "$PUBLIC_BASE_URL" ] && break
    PUBLIC_BASE_URL=""
    sleep 1
  done
  if [ -z "$PUBLIC_BASE_URL" ]; then
    echo "✖ Could not get the ngrok URL (is ngrok authed? run: ngrok config add-authtoken <token>). See /tmp/banglabot-ngrok.log"
    exit 1
  fi
  export PUBLIC_BASE_URL TWILIO_PUBLIC_BASE_URL="$PUBLIC_BASE_URL"
  echo "✔ Public URL: $PUBLIC_BASE_URL"
else
  echo "▶ Skipping ngrok (--no-ngrok): outbound calls cannot reach this machine."
fi

# --- Backend -----------------------------------------------------------------------------------
echo "▶ Starting backend on :8000..."
(cd "$BACKEND" && "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload) &

echo "▶ Waiting for API (first boot creates the database schema)..."
backend_ready=0
for _ in $(seq 1 180); do
  if curl -sf --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    backend_ready=1
    break
  fi
  sleep 1
done
if [ "$backend_ready" -ne 1 ]; then
  echo "✖ Backend did not become ready on :8000 — check DATABASE_URL / the uvicorn log above."
  exit 1
fi
echo "✔ Backend ready"

# --- Frontend ----------------------------------------------------------------------------------
echo "▶ Starting frontend on :3000..."
(cd "$FRONTEND" && NEXT_BACKEND_URL="http://127.0.0.1:8000" npm run dev) &

echo ""
echo "  UI:      http://localhost:3000            (website; portal sign-in at /login)"
echo "  Admin:   http://localhost:3000/admin      (ADMIN_USERNAME / ADMIN_PASSWORD from .env)"
echo "  Test:    clinic/clinic123 · realestate/realestate123 · homeservice/homeservice123 · shop/shop123"
echo "  API:     http://localhost:8000/docs"
if [ -n "$PUBLIC_BASE_URL" ]; then
  echo "  Public:  $PUBLIC_BASE_URL  (Twilio webhooks + media stream)"
fi
echo ""
wait
