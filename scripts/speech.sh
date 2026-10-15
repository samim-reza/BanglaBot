#!/usr/bin/env bash
# Local open-source speech server for phone-call testing (no paid STT/TTS):
#   Parakeet TDT 0.6B v2 (STT) + Silero VAD + Kokoro-82M (TTS) on the laptop GPU (CPU fallback).
#
#   scripts/speech.sh            # first run: uv sync + model download (~2 GB), then serve in the foreground
#
# Env: SPEECH_HOST (127.0.0.1) SPEECH_PORT (8100) SPEECH_SERVER_KEY (optional shared secret; read from
# the repo .env when not exported) SPEECH_DEVICE (auto|cuda|cpu). See speech/README.md for the rest.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/speech"

UV="$(command -v uv || true)"
[ -n "$UV" ] || UV="$HOME/.local/bin/uv"
if [ ! -x "$UV" ]; then
  echo "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

# 1. Python env (only when missing or the lock changed).
if [ ! -x .venv/bin/python ] || [ uv.lock -nt .venv ] || [ pyproject.toml -nt .venv ]; then
  echo "==> uv sync (first run downloads onnxruntime-gpu + CUDA 13/cuDNN wheels, ~2.5 GB)"
  "$UV" sync --frozen
  touch .venv
fi

# 2. Models (int8 always; + fp16 Parakeet when an NVIDIA GPU is present).
if ! "$UV" run --frozen --no-sync python scripts/download_models.py --check >/dev/null 2>&1; then
  echo "==> downloading models into speech/models"
  "$UV" run --frozen --no-sync python scripts/download_models.py
fi

# 3. Share the backend's key when it lives in the repo .env (value is never printed).
if [ -z "${SPEECH_SERVER_KEY:-}" ] && [ -f "$ROOT/.env" ]; then
  key_line="$(grep -E '^SPEECH_SERVER_KEY=' "$ROOT/.env" | tail -n 1 || true)"
  key="${key_line#SPEECH_SERVER_KEY=}"
  key="${key%\"}"; key="${key#\"}"; key="${key%\'}"; key="${key#\'}"
  if [ -n "$key" ]; then export SPEECH_SERVER_KEY="$key"; fi
fi

HOST="${SPEECH_HOST:-127.0.0.1}"
PORT="${SPEECH_PORT:-8100}"
if [ -n "${SPEECH_SERVER_KEY:-}" ]; then
  key_hint="<same value as this server's SPEECH_SERVER_KEY>   (auth ON)"
else
  key_hint="                                                   (auth OFF: no key set)"
fi
cat <<EOF

Backend env (repo .env) for the local speech provider:
  SPEECH_SERVER_URL=http://$HOST:$PORT
  SPEECH_SERVER_KEY=$key_hint

Starting speech server on http://$HOST:$PORT  (Ctrl+C to stop; models load in ~10 s)
EOF

exec "$UV" run --frozen --no-sync python -m server
