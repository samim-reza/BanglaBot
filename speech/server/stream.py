"""One streaming-STT session: mu-law in, VAD endpointing, one transcript per utterance out."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .codec import Float32Array, ulaw_to_float
from .engines import Engines

log = logging.getLogger("speech.stream")

Sender = Callable[[dict[str, Any]], Awaitable[None]]


class SttStream:
    """Transport-agnostic: the websocket route feeds bytes in and supplies ``send``."""

    def __init__(self, engines: Engines, send: Sender, *, silence_ms: int) -> None:
        self._engines = engines
        self._send = send
        self._segmenter = engines.segmenter(silence_ms)
        self._queue: asyncio.Queue[tuple[Float32Array, float]] = asyncio.Queue()
        self._worker = asyncio.create_task(self._transcribe_loop())
        self.utterances = 0

    async def push_ulaw(self, data: bytes) -> None:
        """Feed raw 8 kHz mu-law (any length; Telnyx sends 160-byte / 20 ms frames)."""
        if not data:
            return
        # Silero on one 32 ms window costs ~0.1 ms on CPU, so this stays on the loop.
        for event in self._segmenter.feed(ulaw_to_float(data)):
            if event.kind == "speech_started":
                await self._send({"type": "speech_started"})
                continue
            await self._send({"type": "speech_stopped"})
            if event.audio is not None and event.audio.size:
                self.utterances += 1
                self._queue.put_nowait((event.audio, time.perf_counter()))

    def clear(self) -> None:
        """Drop the utterance being collected (already-queued transcriptions still finish)."""
        self._segmenter.reset()

    async def close(self) -> None:
        self._worker.cancel()
        try:
            await self._worker
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def _transcribe_loop(self) -> None:
        """Serial per connection, so ``completed`` events keep utterance order."""
        while True:
            audio, stopped_at = await self._queue.get()
            try:
                result = await self._engines.transcribe(audio, 8000)
            except Exception as exc:  # noqa: BLE001
                log.exception("transcription failed")
                await self._safe_send({"type": "error", "message": f"transcription failed: {exc}"})
                continue
            latency_ms = round((time.perf_counter() - stopped_at) * 1000)
            log.info("utterance %.2fs -> %d ms: %r", result.audio_seconds, latency_ms, result.text[:80])
            await self._safe_send(
                {
                    "type": "completed",
                    "text": result.text,
                    "confidence": result.confidence,
                    "audio_seconds": result.audio_seconds,
                    "model": self._engines.stt.name,
                    "latency_ms": latency_ms,
                }
            )

    async def _safe_send(self, message: dict[str, Any]) -> None:
        try:
            await self._send(message)
        except Exception:  # noqa: BLE001 - peer went away; nothing to report to
            log.debug("dropped %s: connection closed", message.get("type"))
