#!/usr/bin/env bash
# Starts ngrok + backend + frontend for local development.
# Usage: ./scripts/dev.sh
set -e
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
sleep 4

PUBLIC_BASE_URL=$(curl -s http://127.0.0.1:4040/api/tunnels \
  | python3 -c 'import json,sys; t=json.load(sys.stdin)["tunnels"]; print(next(x["public_url"] for x in t if x["public_url"].startswith("https")))')
if [ -z "$PUBLIC_BASE_URL" ]; then
  echo "✖ Could not get ngrok URL (is ngrok authed? run: ngrok config add-authtoken <token>)"
  exit 1
fi
export PUBLIC_BASE_URL
echo "✔ Public URL: $PUBLIC_BASE_URL"

echo "▶ Starting backend on :8000..."
(cd "$ROOT/backend" && ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000) &

echo "▶ Starting frontend on :5173..."
(cd "$ROOT/frontend" && npm run dev) &

echo ""
echo "  UI:      http://localhost:5173"
echo "  API:     http://localhost:8000/docs"
echo "  Public:  $PUBLIC_BASE_URL  (used for Twilio webhooks)"
echo ""
wait
