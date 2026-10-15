"""HTTP routes: ``GET /health``, ``POST /tts``, ``POST /stt``."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .auth import require_key
from .codec import read_wav, ulaw_to_float
from .engines import FORMATS, Engines, silence
from .stt import SttResult, check_language
from .text import chunk_text

log = logging.getLogger("speech.http")
router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_TTS_CHARS = 5000
_WAV_TYPES = ("audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave")
_ULAW_TYPES = ("audio/basic", "audio/x-mulaw", "audio/mulaw", "audio/pcmu")


def engines_of(request: Request) -> Engines:
    return request.app.state.engines


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Cheap (no subprocess / inference): the backend probes it with a 300 ms timeout."""
    e = engines_of(request)
    return {
        "ok": True,
        "stt": e.stt.name,
        "tts": e.tts.name,
        "device": e.device,
        "voices": ["female", "male", *e.tts.voices],
        "stt_device": e.stt.device,
        "stt_precision": e.stt.precision,
        "tts_device": e.tts.device,
        "vram_mb": e.vram_mb,
        "uptime_s": round(time.time() - e.started_at),
    }


@router.post("/tts", dependencies=[Depends(require_key)])
async def tts(request: Request) -> Response:
    e = engines_of(request)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is empty")
    if len(text) > MAX_TTS_CHARS:
        raise HTTPException(400, f"text longer than {MAX_TTS_CHARS} characters")
    fmt = str(body.get("format") or "ulaw8k")
    if fmt not in FORMATS:
        raise HTTPException(400, f"format must be one of {sorted(FORMATS)}")
    try:
        speed = float(body.get("speed") or 1.0)
        choice = e.tts.resolve(body.get("voice"), body.get("language"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from None

    chunks = chunk_text(text)
    started = time.perf_counter()
    try:
        first = await e.render(chunks[0][0], choice, speed, fmt)
    except ValueError as exc:  # e.g. text that produces no phonemes
        raise HTTPException(400, str(exc)) from None
    first_ms = round((time.perf_counter() - started) * 1000)
    log.info("tts %s/%s first chunk %d ms (%d chunks)", choice.voice, choice.espeak, first_ms, len(chunks))

    async def stream() -> AsyncIterator[bytes]:
        yield first + silence(fmt, chunks[0][1])
        for chunk, pause in chunks[1:]:
            try:
                audio = await e.render(chunk, choice, speed, fmt)
            except Exception:  # noqa: BLE001 - headers are gone; end the audio cleanly
                log.exception("tts chunk failed; truncating response")
                return
            yield audio + silence(fmt, pause)

    headers = {"X-Voice": choice.voice, "X-First-Chunk-Ms": str(first_ms)}
    if len(chunks) == 1:
        return Response(first, media_type=FORMATS[fmt], headers=headers)
    return StreamingResponse(stream(), media_type=FORMATS[fmt], headers=headers)


@router.post("/stt", dependencies=[Depends(require_key)])
async def stt(request: Request, language: str = "en") -> JSONResponse:
    e = engines_of(request)
    try:
        check_language(language)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty body")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "audio too large")
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    is_wav = content_type in _WAV_TYPES or (content_type not in _ULAW_TYPES and data[:4] == b"RIFF")

    def job() -> SttResult:
        audio, rate = read_wav(data) if is_wav else (ulaw_to_float(data), 8000)
        return e.stt.transcribe(np.asarray(audio, dtype=np.float32), rate)

    try:
        result = await e.run_stt_job(job)
    except ValueError as exc:
        raise HTTPException(400, f"could not decode audio: {exc}") from None
    return JSONResponse(
        {
            "text": result.text,
            "audio_seconds": result.audio_seconds,
            "confidence": result.confidence,
            "model": e.stt.name,
        }
    )
