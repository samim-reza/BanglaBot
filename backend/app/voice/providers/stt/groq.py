"""Groq Whisper (free tier) as an STT provider: backend VAD + one request per utterance.

Whisper transcribes files, not streams, so :class:`EnergyVAD` cuts the
caller's audio into utterances; each one is wrapped as an 8 kHz WAV and posted
to Groq's OpenAI-compatible transcription endpoint. Utterances are transcribed
one at a time, in order, so turns never arrive shuffled.

Whisper invents words from noise (a cough comes back as "Thank you"), and
Groq's ``no_speech_prob`` is always 0. The average log-probability tells them
apart: noise scored -1.05..-1.29, speech -0.13..-0.79 (measured on real calls),
so an utterance whose every segment is below -1.0 is dropped.

Groq bills at least ~10 s per request, so usage reports both the real audio
seconds and the billed ones. On an auth or quota error the provider is paused
and the session closes, so the bridge reconnects to the next provider.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any, AsyncIterator

import httpx
import structlog

from app.voice.codec import ulaw_to_pcm16, wav_bytes
from app.voice.providers.stt import health
from app.voice.providers.stt.vad import EnergyVAD
from app.voice.stt import STTEvent

logger = structlog.get_logger(__name__)

TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MIN_BILLED_SECONDS = 10.0
#: Whisper's prompt window is ~224 tokens.
PROMPT_MAX_CHARS = 400


def is_noise(segments: list[Any], threshold: float = -1.0) -> bool:
    """Every segment scored below ``threshold`` → the "words" were invented from noise."""
    scores: list[float] = []
    for segment in segments:
        value = segment.get("avg_logprob") if isinstance(segment, dict) else getattr(segment, "avg_logprob", None)
        if value is not None:
            scores.append(float(value))
    return bool(scores) and all(score < threshold for score in scores)


class GroqWhisperSTT:
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        language: str | None,
        prompt: str = "",
        model: str = "whisper-large-v3-turbo",
        noise_logprob: float = -1.0,
        vad: EnergyVAD | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.language = language
        self.prompt = " ".join(str(prompt or "").split())[:PROMPT_MAX_CHARS]
        self.model = model
        self.noise_logprob = noise_logprob
        self.vad = vad or EnergyVAD()
        self._transport = transport
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None
        self._events: asyncio.Queue[STTEvent] = asyncio.Queue()
        self._utterances: asyncio.Queue[tuple[int, int, bytes]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._seq = 0
        self._generation = 0
        self._closed = False
        self.audio_bytes = 0
        self.audio_seconds = 0.0
        self.billed_seconds = 0.0
        self.requests = 0
        self.dropped_noise = 0

    @property
    def connected(self) -> bool:
        return self._client is not None and not self._closed

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout, connect=5.0),
            headers={"Authorization": f"Bearer {self.api_key}"},
            transport=self._transport,
        )
        self._worker = asyncio.create_task(self._work())

    async def send_audio_b64(self, payload: str) -> None:
        if not self.connected or not payload:
            return
        try:
            data = base64.b64decode(payload)
        except (binascii.Error, ValueError):
            return
        self.audio_bytes += len(data)
        for event in self.vad.push(data):
            self._on_vad(event.type, event.audio)

    def _on_vad(self, kind: str, audio: bytes) -> None:
        if kind == "start":
            self._seq += 1
            self._events.put_nowait(STTEvent("speech_started", item_id=f"groq-{self._seq}"))
            return
        self._events.put_nowait(STTEvent("speech_stopped", item_id=f"groq-{self._seq}"))
        if kind == "end" and audio:
            self._utterances.put_nowait((self._generation, self._seq, audio))

    async def clear_input(self) -> None:
        """Drop the utterance being collected and any not yet sent to Groq."""
        self._generation += 1
        self.vad.reset()

    async def _work(self) -> None:
        while not self._closed:
            generation, seq, audio = await self._utterances.get()
            if generation != self._generation:
                continue
            try:
                text = await self.transcribe(audio)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — one failed utterance must not deafen the call
                self._events.put_nowait(STTEvent("error", text=f"groq_stt_{type(exc).__name__}: {str(exc)[:160]}"))
                continue
            if text and generation == self._generation:
                self._events.put_nowait(STTEvent("completed", text=text, item_id=f"groq-{seq}"))

    async def transcribe(self, ulaw: bytes) -> str:
        """One utterance (8 kHz μ-law) → text ('' for noise)."""
        if self._client is None:
            return ""
        seconds = len(ulaw) / 8000
        data = {"model": self.model, "response_format": "verbose_json", "temperature": "0"}
        if self.language:
            data["language"] = self.language
        if self.prompt:
            data["prompt"] = self.prompt
        files = {"file": ("utterance.wav", wav_bytes(ulaw_to_pcm16(ulaw), 8000), "audio/wav")}
        response = await self._client.post(TRANSCRIBE_URL, data=data, files=files)
        if response.status_code != 200:
            if response.status_code in (401, 403, 429):
                health.mark_down(self.name, 60.0, reason=f"http_{response.status_code}")
                await self._shutdown(f"groq_unavailable_http_{response.status_code}")
            raise RuntimeError(f"http_{response.status_code}: {response.text[:160]}")
        self.requests += 1
        self.audio_seconds += seconds
        self.billed_seconds += max(seconds, MIN_BILLED_SECONDS)
        body = response.json()
        text = " ".join(str(body.get("text") or "").split())
        if text and is_noise(body.get("segments") or [], self.noise_logprob):
            self.dropped_noise += 1
            await logger.ainfo("groq_stt_noise_dropped", seconds=round(seconds, 2))
            return ""
        return text

    async def events(self) -> AsyncIterator[STTEvent]:
        while True:
            event = await self._events.get()
            yield event
            if event.type == "closed":
                return

    def usage(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "audio_seconds": round(self.audio_seconds, 2),
            "billed_seconds": round(self.billed_seconds, 2),
            "streamed_seconds": round(self.audio_bytes / 8000, 2),
            "requests": self.requests,
            "dropped_noise": self.dropped_noise,
        }

    async def _shutdown(self, reason: str = "") -> None:
        if self._closed:
            return
        self._closed = True
        self._events.put_nowait(STTEvent("closed", text=reason))

    async def close(self) -> None:
        await self._shutdown()
        worker, self._worker = self._worker, None
        if worker is not None and worker is not asyncio.current_task():
            worker.cancel()
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


__all__ = ["GroqWhisperSTT", "is_noise"]
