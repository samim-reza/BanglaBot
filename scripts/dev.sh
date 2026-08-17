#!/usr/bin/env bash
# Starts ngrok + backend + frontend for local development.
# Usage: ./scripts/dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT

# Stop any previously running instances so a plain re-run always works.
pkill -f "venv/bin/uvicorn app.main" 2>/dev/null || true
pkill -f "ngrok http 8000" 2>/dev/null || true
pkill -f "$ROOT/frontend/node_modules/.bin/vite" 2>/dev/null || true
sleep 1

echo "▶ Starting ngrok tunnel to port 8000..."
ngrok http 8000 --log=stdout > /tmp/banglabot-ngrok.log &

PUBLIC_BASE_URL=""
for _ in $(seq 1 20); do
  PUBLIC_BASE_URL=$(curl -sf --max-time 2 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
    | python3 -c 'import json,sys
try:
    tunnels=json.load(sys.stdin).get("tunnels") or []
    print(next(x["public_url"] for x in tunnels if str(x.get("public_url","")).startswith("https")))
except Exception:
    sys.exit(1)
' 2>/dev/null) && [ -n "$PUBLIC_BASE_URL" ] && break
  PUBLIC_BASE_URL=""
  sleep 1
done
if [ -z "$PUBLIC_BASE_URL" ]; then
  echo "✖ Could not get ngrok URL (is ngrok authed? run: ngrok config add-authtoken <token>)"
  exit 1
fi
export PUBLIC_BASE_URL
echo "✔ Public URL: $PUBLIC_BASE_URL"

echo "▶ Starting backend on :8000..."
# --reload so backend code changes apply without restarting dev.sh
(cd "$ROOT/backend" && ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &

echo "▶ Waiting for API..."
backend_ready=0
for _ in $(seq 1 90); do
  if curl -sf --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    backend_ready=1
    break
  fi
  sleep 1
done
if [ "$backend_ready" -ne 1 ]; then
  echo "✖ Backend did not become ready on :8000 — check DATABASE_URL / Postgres"
  exit 1
fi
echo "✔ Backend ready"

echo "▶ Starting frontend on :5173..."
(cd "$ROOT/frontend" && npm run dev) &

echo ""
echo "  UI:      http://localhost:5173"
echo "  API:     http://localhost:8000/docs"
echo "  Public:  $PUBLIC_BASE_URL  (used for Twilio webhooks)"
echo ""
wait
