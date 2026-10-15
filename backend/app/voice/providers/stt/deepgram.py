"""Deepgram streaming speech-to-text (Nova-3) over a websocket.

Raw μ-law frames go in as binary messages exactly as Telnyx sends them (no
transcoding). Deepgram's events map onto the bridge's :class:`STTEvent` set:

* ``SpeechStarted`` / first interim words → ``speech_started``
* interim ``Results`` → ``delta`` (the utterance so far)
* ``is_final`` results are collected; ``speech_final`` (endpointing),
  ``UtteranceEnd`` or a ``Finalize`` reply end the utterance → ``speech_stopped``
  + ``completed`` with the joined finals

Deepgram closes a socket that receives nothing for ~10 s, and the bridge stops
forwarding caller audio while the agent speaks (half duplex, to not pay for
it), so a ``KeepAlive`` goes out whenever no audio flowed for a few seconds,
and a ``Finalize`` flushes words that were still interim when audio stopped.

Deepgram's own endpointing is slow on a live phone line: while audio keeps
flowing (Telnyx streams the caller's silence too) ``speech_final`` arrived
5.8–7.5 s after the caller stopped (measured 2026-10-16). So the backend's
energy VAD watches the same frames and sends ``Finalize`` once the caller has
been quiet for ``end_silence_ms`` — the reply then lands in well under a second.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from collections.abc import Sequence
from typing import Any, AsyncIterator
from urllib.parse import urlencode

import structlog
import websockets

from app.voice.providers.stt.vad import EnergyVAD
from app.voice.stt import STTEvent

logger = structlog.get_logger(__name__)

LISTEN_URL = "wss://api.deepgram.com/v1/listen"
#: Send a Finalize when interim words are pending and no audio came for this long.
FINALIZE_AFTER_SECONDS = 0.6


def clean_keyterms(terms: Sequence[str], limit: int) -> list[str]:
    """Distinct, trimmed names (≤ 60 chars each), at most ``limit`` of them."""
    seen: list[str] = []
    for term in terms:
        value = " ".join(str(term or "").split())[:60]
        if value and value.lower() not in {s.lower() for s in seen}:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def listen_url(
    *, model: str, language: str | None, keyterms: Sequence[str] = (), endpointing_ms: int = 300, utterance_end_ms: int = 1000
) -> str:
    params: list[tuple[str, str]] = [
        ("model", model),
        ("encoding", "mulaw"),
        ("sample_rate", "8000"),
        ("channels", "1"),
        ("interim_results", "true"),
        ("endpointing", str(endpointing_ms)),
        ("utterance_end_ms", str(max(1000, utterance_end_ms))),
        ("vad_events", "true"),
        ("smart_format", "true"),
    ]
    if language:
        params.append(("language", language))
    params.extend(("keyterm", term) for term in keyterms)
    return f"{LISTEN_URL}?{urlencode(params)}"


class DeepgramSTT:
    name = "deepgram"

    def __init__(
        self,
        *,
        api_key: str,
        language: str | None,
        keyterms: Sequence[str] = (),
        model: str = "nova-3",
        endpointing_ms: int = 300,
        utterance_end_ms: int = 1000,
        max_keyterms: int = 40,
        end_silence_ms: int = 600,
        keepalive_seconds: float = 5.0,
        tick_seconds: float = 0.2,
        connector: Any = None,
    ) -> None:
        self.api_key = api_key
        self.language = language
        self.model = model
        # Keyterm prompting is an English feature; other languages would reject the socket.
        terms = clean_keyterms(keyterms, max_keyterms) if (language or "en").startswith("en") else []
        self.url = listen_url(model=model, language=language, keyterms=terms, endpointing_ms=endpointing_ms, utterance_end_ms=utterance_end_ms)
        self.keepalive_seconds = keepalive_seconds
        self.tick_seconds = tick_seconds
        self._connector = connector or websockets.connect
        self._vad = EnergyVAD(end_silence_ms=end_silence_ms)
        self._ws: Any = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._finals: list[str] = []
        self._in_speech = False
        self._utterance = 0
        self._pending_interim = False
        self._last_send = 0.0
        self._last_audio = 0.0
        self.audio_bytes = 0
        self.billed_seconds = 0.0
        self.request_id = ""

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def connect(self) -> None:
        self._ws = await self._connector(
            self.url,
            additional_headers={"Authorization": f"Token {self.api_key}"},
            max_size=4_000_000,
            open_timeout=5,
        )
        self._last_send = self._last_audio = time.monotonic()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _send(self, message: str | bytes) -> bool:
        if self._ws is None:
            return False
        try:
            await self._ws.send(message)
        except websockets.ConnectionClosed:
            self._ws = None
            return False
        self._last_send = time.monotonic()
        return True

    async def send_audio_b64(self, payload: str) -> None:
        if self._ws is None or not payload:
            return
        try:
            data = base64.b64decode(payload)
        except (binascii.Error, ValueError):
            return
        if data and await self._send(data):
            self.audio_bytes += len(data)
            self._last_audio = self._last_send
            # The caller went quiet after speaking: flush now instead of waiting for Deepgram's endpointing.
            if any(event.type in ("end", "discard") for event in self._vad.push(data)):
                await self._finalize()

    async def _finalize(self) -> None:
        self._pending_interim = False
        await self._send(json.dumps({"type": "Finalize"}))

    async def clear_input(self) -> None:
        """Forget finals collected for the current utterance (barge-in reset)."""
        self._finals.clear()
        self._vad.reset()

    async def keepalive(self) -> None:
        await self._send(json.dumps({"type": "KeepAlive"}))

    async def _keepalive_loop(self) -> None:
        while self._ws is not None:
            await asyncio.sleep(self.tick_seconds)
            now = time.monotonic()
            if self._pending_interim and now - self._last_audio >= FINALIZE_AFTER_SECONDS:
                await self._finalize()
            elif now - self._last_send >= self.keepalive_seconds:
                await self.keepalive()

    # ------------------------------------------------------------------ events
    async def events(self) -> AsyncIterator[STTEvent]:
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw in ws:
                if isinstance(raw, (bytes, bytearray)):
                    continue
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                for event in self.translate(message):
                    yield event
        except websockets.ConnectionClosed as exc:
            self._ws = None
            yield STTEvent("closed", text=str(exc))
            return
        self._ws = None
        yield STTEvent("closed")

    def translate(self, message: dict[str, Any]) -> list[STTEvent]:
        """One Deepgram message → zero or more bridge events."""
        kind = str(message.get("type") or "")
        if kind == "SpeechStarted":
            return self._start(message)
        if kind == "Results":
            alternatives = (message.get("channel") or {}).get("alternatives") or [{}]
            text = str(alternatives[0].get("transcript") or "").strip()
            if message.get("is_final"):
                self._pending_interim = False
                if text:
                    self._finals.append(text)
                if message.get("speech_final") or message.get("from_finalize"):
                    return self._end(message)
                return [*self._start(message), STTEvent("delta", text=" ".join(self._finals), item_id=self._item(), raw=message)] if text else []
            if not text:
                return []
            self._pending_interim = True
            return [*self._start(message), STTEvent("delta", text=" ".join([*self._finals, text]), item_id=self._item(), raw=message)]
        if kind == "UtteranceEnd":
            return self._end(message)
        if kind == "Metadata":
            self.billed_seconds = float(message.get("duration") or self.billed_seconds or 0.0)
            self.request_id = str(message.get("request_id") or self.request_id)
            return []
        if kind.lower() == "error" or message.get("err_code"):
            detail = message.get("description") or message.get("err_msg") or message.get("message") or "deepgram_error"
            return [STTEvent("error", text=str(detail), raw=message)]
        return []

    def _item(self) -> str:
        return f"dg-{self._utterance}"

    def _start(self, message: dict[str, Any]) -> list[STTEvent]:
        if self._in_speech:
            return []
        self._in_speech = True
        self._utterance += 1
        return [STTEvent("speech_started", item_id=self._item(), raw=message)]

    def _end(self, message: dict[str, Any]) -> list[STTEvent]:
        text = " ".join(self._finals).strip()
        self._finals.clear()
        events: list[STTEvent] = []
        if self._in_speech:
            events.append(STTEvent("speech_stopped", item_id=self._item(), raw=message))
            self._in_speech = False
        if text:
            events.append(STTEvent("completed", text=text, item_id=self._item(), raw=message))
        return events

    # --------------------------------------------------------------- lifecycle
    def usage(self) -> dict[str, Any]:
        seconds = round(self.audio_bytes / 8000, 2)
        return {
            "provider": self.name,
            "model": self.model,
            "audio_seconds": seconds,
            "billed_seconds": round(self.billed_seconds, 2) or seconds,
            "request_id": self.request_id,
        }

    async def close(self) -> None:
        task, self._keepalive_task = self._keepalive_task, None
        if task is not None:
            task.cancel()
        ws = self._ws
        if ws is None:
            return
        await self._send(json.dumps({"type": "CloseStream"}))
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
        self._ws = None


__all__ = ["DeepgramSTT", "clean_keyterms", "listen_url"]
