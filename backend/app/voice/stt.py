"""Streaming speech-to-text over OpenAI's transcription-only Realtime session.

This is the *ears* of the cascade pipeline: Twilio μ-law frames go in, server
VAD marks speech start/stop, and finished utterances come back as text. No
speech model reasons or speaks here — that is ``gpt-5.4-mini`` + Azure TTS —
so the only OpenAI audio cost is the transcription model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import structlog
import websockets

logger = structlog.get_logger(__name__)

TRANSCRIPTION_URL = "wss://api.openai.com/v1/realtime?intent=transcription"


@dataclass(slots=True)
class STTEvent:
    #: speech_started | speech_stopped | delta | completed | error | closed
    type: str
    text: str = ""
    item_id: str = ""
    raw: dict[str, Any] | None = None


class TranscriptionStream:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        language: str | None,
        prompt: str = "",
        vad_threshold: float = 0.5,
        vad_prefix_padding_ms: int = 300,
        vad_silence_duration_ms: int = 600,
        noise_reduction: str | None = "far_field",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        self.prompt = prompt
        self.vad_threshold = vad_threshold
        self.vad_prefix_padding_ms = vad_prefix_padding_ms
        self.vad_silence_duration_ms = vad_silence_duration_ms
        self.noise_reduction = noise_reduction
        self._ws: Any = None
        self.session_id: str | None = None

    def _session_body(self) -> dict[str, Any]:
        transcription: dict[str, Any] = {"model": self.model}
        if self.language:
            transcription["language"] = self.language
        if self.prompt:
            transcription["prompt"] = self.prompt
        audio_input: dict[str, Any] = {
            "format": {"type": "audio/pcmu"},
            "transcription": transcription,
            "turn_detection": {
                "type": "server_vad",
                "threshold": self.vad_threshold,
                "prefix_padding_ms": self.vad_prefix_padding_ms,
                "silence_duration_ms": self.vad_silence_duration_ms,
            },
        }
        if self.noise_reduction:
            audio_input["noise_reduction"] = {"type": self.noise_reduction}
        return {"type": "transcription", "audio": {"input": audio_input}}

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            TRANSCRIPTION_URL,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            max_size=8_000_000,
        )
        await self._ws.send(json.dumps({"type": "session.update", "session": self._session_body()}))

    async def send_audio_b64(self, payload: str) -> None:
        """Forward one Twilio media payload (base64 μ-law) unchanged."""
        if self._ws is None or not payload:
            return
        try:
            await self._ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": payload}))
        except websockets.ConnectionClosed:
            # Late frames after the session closed are not an error for the call.
            self._ws = None

    async def clear_input(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
        except websockets.ConnectionClosed:
            self._ws = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def events(self) -> AsyncIterator[STTEvent]:
        """Yield normalized events until the socket closes."""
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                kind = str(event.get("type") or "")
                if kind in {"session.created", "session.updated"}:
                    session = event.get("session") or {}
                    self.session_id = session.get("id") or self.session_id
                    continue
                if kind == "input_audio_buffer.speech_started":
                    yield STTEvent("speech_started", item_id=str(event.get("item_id") or ""), raw=event)
                elif kind == "input_audio_buffer.speech_stopped":
                    yield STTEvent("speech_stopped", item_id=str(event.get("item_id") or ""), raw=event)
                elif kind == "conversation.item.input_audio_transcription.delta":
                    yield STTEvent("delta", text=str(event.get("delta") or ""), item_id=str(event.get("item_id") or ""), raw=event)
                elif kind == "conversation.item.input_audio_transcription.completed":
                    yield STTEvent("completed", text=str(event.get("transcript") or "").strip(), item_id=str(event.get("item_id") or ""), raw=event)
                elif kind == "conversation.item.input_audio_transcription.failed":
                    yield STTEvent("error", text=str((event.get("error") or {}).get("message") or "transcription_failed"), raw=event)
                elif kind == "error":
                    yield STTEvent("error", text=str((event.get("error") or {}).get("message") or "stt_error"), raw=event)
        except websockets.ConnectionClosed as exc:
            self._ws = None
            yield STTEvent("closed", text=str(exc))
            return
        # Socket iteration ended without an exception (clean close).
        self._ws = None
        yield STTEvent("closed")

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
