# BanglaBot local speech server

A free, open-source speech server for phone-call testing. It runs on the developer's laptop GPU and
falls back to CPU, so testing calls doesn't use paid STT or TTS. The BanglaBot backend calls it through its
`local` STT/TTS providers (`backend/app/voice/providers/{stt,tts}/local.py`).

| Part | Model | License | On disk | Runtime |
|---|---|---|---|---|
| STT | NVIDIA **Parakeet TDT 0.6B v2** (English), via [onnx-asr](https://github.com/istupakov/onnx-asr) | CC-BY-4.0 (model; credit NVIDIA), MIT (onnx-asr) | fp16 1.26 GB (GPU) + int8 0.66 GB (CPU) | onnxruntime CUDA / CPU |
| VAD | **Silero VAD v6** (`silero_vad.onnx`, 8 kHz native) | MIT | 2.3 MB | onnxruntime CPU |
| TTS | **Kokoro-82M v1.0** via [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | Apache-2.0 (model + voices), MIT (kokoro-onnx) | 326 MB + 28 MB voices | onnxruntime CUDA / CPU |

Sources: `istupakov/parakeet-tdt-0.6b-v2-onnx` (int8, config and vocab) and `ysdede/parakeet-tdt-0.6b-v2-onnx`
(the fp16 export of the same weights) on Hugging Face, the `thewh1teagle/kokoro-onnx` `model-files-v1.0` release,
and `snakers4/silero-vad` v6.2.1. Every revision is pinned in `server/models.py`.
Kokoro converts text to phonemes with espeak-ng, which comes bundled through `espeakng-loader` and `phonemizer`. Both are
GPL-3.0. That's fine for local use, but check the licence before you redistribute.

## Run

```bash
scripts/speech.sh           # from the repo root
```

On the first run it does `uv sync`, about 2.5 GB, because onnxruntime-gpu pulls the CUDA 13 and cuDNN 9 wheels. It then downloads the
models, about 2.2 GB, and serves in the foreground on `127.0.0.1:8100`. Models load and warm up in about 10 s, and the port
only accepts requests once they're ready. Press Ctrl+C to stop.

To run the steps by hand from `speech/`:

```bash
uv sync
uv run python scripts/download_models.py        # int8 always, + fp16 if an NVIDIA GPU is present
uv run python scripts/smoke.py                  # offline: Kokoro -> mu-law 8k -> VAD -> Parakeet, timings + VRAM
uv run python -m server                         # serve
uv run python scripts/client_check.py           # against a running server: /health, /tts, /stt, WS /stt
```

Add this to the backend's repo `.env`:

```
SPEECH_SERVER_URL=http://127.0.0.1:8100
SPEECH_SERVER_KEY=some-long-random-string   # optional; speech.sh reuses it from the repo .env
```

### Settings (environment)

| Variable | Default | Meaning |
|---|---|---|
| `SPEECH_HOST` / `SPEECH_PORT` | `127.0.0.1` / `8100` | bind address |
| `SPEECH_SERVER_KEY` | unset | when set, `X-Speech-Key` is required (WS also accepts `?key=`); `/health` stays open |
| `SPEECH_DEVICE` | `auto` | `auto` / `cuda` / `cpu`; `SPEECH_STT_DEVICE` and `SPEECH_TTS_DEVICE` override it per engine |
| `SPEECH_STT_PRECISION` | `auto` | `auto` (fp16 on CUDA, int8 on CPU) / `fp16` / `int8` / `fp32` |
| `SPEECH_VOICE_FEMALE` / `SPEECH_VOICE_MALE` | `af_heart` / `am_michael` | Kokoro voices for `female` / `male` (English) |
| `SPEECH_SILENCE_MS` | `600` | default end-of-utterance silence (the WS `silence_ms` query overrides it) |
| `SPEECH_MIN_SPEECH_MS` / `SPEECH_PRE_ROLL_MS` | `200` / `300` | shortest speech that counts, and audio kept from before the trigger |
| `SPEECH_VAD_THRESHOLD` / `SPEECH_VAD_NEG_THRESHOLD` | `0.5` / `0.35` | Silero speech and silence probabilities |
| `SPEECH_MAX_UTTERANCE_S` | `25` | force-cut very long turns |
| `SPEECH_GPU_MEM_MB_STT` / `SPEECH_GPU_MEM_MB_TTS` | `2048` / `1536` | onnxruntime arena caps |
| `SPEECH_MODELS_DIR` | `speech/models` | model location |

## API contract

**`GET /health`** returns
`{"ok": true, "stt": "nemo-parakeet-tdt-0.6b-v2", "tts": "kokoro-82m-v1.0", "device": "cuda|cpu", "voices": ["female","male","af_heart",...]}`.
It also returns `stt_device`, `stt_precision`, `tts_device`, `vram_mb` and `uptime_s`. It's cheap to call because the backend probes it with a 300 ms timeout.

**`POST /tts`** takes the JSON body `{"text": str, "voice": "female"|"male"|<kokoro id>, "language": "en", "speed": 1.0, "format": "ulaw8k"|"pcm16_24k"}`
and returns raw audio:
- `ulaw8k` returns `audio/basic` (G.711 mu-law, 8 kHz, mono).
- `pcm16_24k` returns `audio/L16;rate=24000` (little-endian int16).

Empty text, an unknown voice, an unsupported language or a bad format returns 400. Languages are `en` (US), `en-gb`, `es`, `fr`, `hi`,
`it` and `pt`. Bengali isn't supported. With plain `en`, an explicit voice keeps its own accent, so `b*` voices sound British.
Text is split into chunks of 200 characters or less. A typical reply is one chunk and one model call. Longer text streams back chunk by chunk with
short pauses, and the `X-First-Chunk-Ms` header reports how long the first chunk took to synthesize.

**`WS /stt?language=en&silence_ms=600`**
- Client sends `{"type":"audio","audio":"<base64 mu-law 8 kHz>"}`, which is the Telnyx media payload unchanged, usually 20 ms (160 bytes) per frame.
  It can also send `{"type":"clear"}` to drop the utterance being collected. Binary frames of raw mu-law also work.
- Server sends `{"type":"speech_started"}`, `{"type":"speech_stopped"}`, then one
  `{"type":"completed","text":str,"confidence":float,"audio_seconds":float,"model":str,"latency_ms":int}` per utterance, or
  `{"type":"error","message":str}`. It never sends `partial`.
- If the language isn't English, the server sends an `error` event and closes with code 1008. Parakeet v2 only does English.
- Any `prompt` query parameter is ignored, because Parakeet can't take prompts.

**`POST /stt?language=en`** takes a body of raw mu-law 8 kHz bytes (`audio/basic`) or a WAV file (`audio/wav`: PCM 8/16/24/32, float,
mu-law or A-law, any sample rate). It returns `{"text": str, "audio_seconds": float, "confidence": float, "model": str}`. Audio longer than 25 s is
decoded in 25 s windows.

### How it works

- One process holds the models: Parakeet, Kokoro and a shared Silero session. Each model has its own single-thread executor. That runs
  inference off the event loop and also queues requests per model, while STT and TTS still run at the same time. Each WebSocket keeps its own VAD
  state and transcribes in order, so `completed` events arrive in utterance order. Several calls at once work fine.
- Endpointing works like this. Silero runs at 8 kHz on 32 ms windows. Speech starts once 200 ms is voiced, and 300 ms of pre-roll is kept. The utterance ends
  after `silence_ms` of silence and keeps 200 ms of trailing audio. The whole utterance is upsampled to 16 kHz and decoded once.
- Audio conversion is pure NumPy, because `audioop` is gone in Python 3.13. That covers G.711 mu-law and a polyphase windowed-sinc resampler (24k to 8k, 8k to 16k, any rate for WAV).
- Every new input shape on CUDA re-plans about 70 cuDNN convolutions, which costs about 150 ms. To avoid that, the server pads utterances to fixed 8, 16 or 25 s
  buckets and passes the true length, which the encoder masks. A typical turn then decodes in under 100 ms, and the output is identical to the unpadded decode.
- After long inputs, Kokoro hands its GPU memory back (arena shrinkage), so VRAM stays flat.

## Measured on the dev laptop

The laptop has an RTX 3050 Laptop (4 GB), an i5-12450H, the 580 driver and onnxruntime-gpu 1.31 with CUDA 13. Other desktop apps were running.

| | GPU (fp16 STT) | CPU only (int8 STT) |
|---|---|---|
| Startup (load + warm-up) | ~8–10 s | ~6 s |
| TTS, 1.7 s sentence | ~240 ms | ~950 ms |
| TTS, 5.8 s sentence | ~350–450 ms (RTF ≈ 0.07) | ~2.7 s (RTF ≈ 0.47) |
| STT, 6 s utterance (8k mu-law in) | ~80–120 ms | ~500–650 ms |
| WS: end of speech → `completed` | ≈ silence_ms (600) + ~80 ms | ≈ silence_ms + ~600 ms |
| VRAM (whole process) | ~2.1–2.2 GB steady (cap ≈ 2.5 GB) | 0 |

With four WebSocket calls streaming at once, each `completed` still arrived about 70 ms after its `speech_stopped`.

## Caveats

- Recognition is English only, and there's no keyword or name boosting. Proper names can come back misspelled, for example "Rahman" as "Rahan".
- Switching between padding buckets costs one ~250 ms re-plan. That only happens for turns longer than 8 s.
- When a wrong key is used, uvicorn logs "ASGI callable returned without completing handshake" after the 401 denial. The log line is harmless.
- `onnxruntime-gpu` 1.31 is built for CUDA 13, so the driver must support CUDA 13 (driver 580 or newer). On older drivers, use `SPEECH_DEVICE=cpu`.
