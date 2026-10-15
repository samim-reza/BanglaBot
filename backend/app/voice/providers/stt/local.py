"""The local open-source speech server (``speech/``, laptop GPU) as an STT provider.

Contract: websocket ``{SPEECH_SERVER_URL as ws}/stt?language=en&silence_ms=600``
with header ``X-Speech-Key``. The client sends ``{"type":"audio","audio":<base64
μ-law 8k>}`` (the Telnyx payload, untouched) and ``{"type":"clear"}``; the server
answers ``speech_started`` / ``speech_stopped`` / ``partial`` / ``completed`` /
``error``. Free to run, so it leads the chain whenever the laptop is up.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, AsyncIterator
from urllib.parse import urlencode

import websockets

from app.voice.codec import b64_decoded_len
from app.voice.providers.stt.health import ws_base
from app.voice.stt import STTEvent


class LocalSTT:
    name = "local"

    def __init__(
        self,
        *,
        base_url: str,
        key: str | None,
        language: str | None,
        prompt: str = "",
        keyterms: Sequence[str] = (),
        silence_ms: int = 600,
        connector: Any = None,
    ) -> None:
        params: dict[str, str] = {"language": language or "en", "silence_ms": str(silence_ms)}
        # Names ride in the prompt (the server's Whisper-style decoder takes one).
        extra = [str(term) for term in keyterms if term and str(term) not in prompt]
        full_prompt = " ".join([prompt, *extra]).strip()
        if full_prompt:
            params["prompt"] = full_prompt[:500]
        self.url = f"{ws_base(base_url)}/stt?{urlencode(params)}"
        self.key = key
        self.language = language
        self._connector = connector or websockets.connect
        self._ws: Any = None
        self._utterance = 0
        self.audio_bytes = 0
        self.transcribed_seconds = 0.0
        self.model = ""

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def connect(self) -> None:
        headers = {"X-Speech-Key": self.key} if self.key else {}
        self._ws = await self._connector(self.url, additional_headers=headers, max_size=2_000_000, open_timeout=3)

    async def _send(self, message: dict[str, Any]) -> bool:
        if self._ws is None:
            return False
        try:
            await self._ws.send(json.dumps(message))
        except websockets.ConnectionClosed:
            self._ws = None
            return False
        return True

    async def send_audio_b64(self, payload: str) -> None:
        if payload and await self._send({"type": "audio", "audio": payload}):
            self.audio_bytes += b64_decoded_len(payload)

    async def clear_input(self) -> None:
        await self._send({"type": "clear"})

    async def events(self) -> AsyncIterator[STTEvent]:
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw in ws:
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                event = self.translate(message)
                if event is not None:
                    yield event
        except websockets.ConnectionClosed as exc:
            self._ws = None
            yield STTEvent("closed", text=str(exc))
            return
        self._ws = None
        yield STTEvent("closed")

    def translate(self, message: dict[str, Any]) -> STTEvent | None:
        kind = str(message.get("type") or "")
        if kind == "speech_started":
            self._utterance += 1
            return STTEvent("speech_started", item_id=self._item(), raw=message)
        if kind == "speech_stopped":
            return STTEvent("speech_stopped", item_id=self._item(), raw=message)
        if kind == "partial":
            return STTEvent("delta", text=str(message.get("text") or ""), item_id=self._item(), raw=message)
        if kind == "completed":
            self.transcribed_seconds += float(message.get("audio_seconds") or 0.0)
            self.model = str(message.get("model") or self.model)
            return STTEvent("completed", text=" ".join(str(message.get("text") or "").split()), item_id=self._item(), raw=message)
        if kind == "error":
            return STTEvent("error", text=str(message.get("message") or "local_stt_error"), raw=message)
        return None

    def _item(self) -> str:
        return f"local-{self._utterance}"

    def usage(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model or "local",
            "audio_seconds": round(self.audio_bytes / 8000, 2),
            "billed_seconds": 0.0,
            "transcribed_seconds": round(self.transcribed_seconds, 2),
        }

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass


__all__ = ["LocalSTT"]
