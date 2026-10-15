"""The contracts every provider implements.

They mirror what the call bridge already uses (``voice/stt.TranscriptionStream``,
``voice/tts.AzureSpeechTTS``, ``voice/llm.ChatLLM``), so the bridge and the
text sessions switch providers without changing how they talk to them.

Audio on the phone path is always 8 kHz μ-law (PCMU): STT sessions receive it
base64-encoded exactly as Telnyx sends it, TTS engines return raw μ-law bytes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any, Protocol, runtime_checkable

from app.voice.llm import LLMReply
from app.voice.stt import STTEvent


@runtime_checkable
class STTSession(Protocol):
    """One streaming transcription session for one call.

    Events (:class:`STTEvent`): ``speech_started``, ``speech_stopped``,
    ``delta`` (partial text), ``completed`` (final text of one utterance),
    ``error``.
    """

    #: Provider name, e.g. "deepgram" (finance metering + logs).
    name: str

    async def connect(self) -> None: ...

    async def send_audio_b64(self, payload: str) -> None: ...

    async def clear_input(self) -> None: ...

    @property
    def connected(self) -> bool: ...

    def events(self) -> AsyncIterator[STTEvent]: ...

    async def close(self) -> None: ...

    def usage(self) -> dict[str, Any]:
        """Billable usage so far, at least ``{"provider", "model", "audio_seconds"}``."""
        ...


@runtime_checkable
class TTSEngine(Protocol):
    """Text → 8 kHz μ-law audio; implementations cache through ``voice/tts_cache``."""

    name: str

    async def synthesize(
        self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None
    ) -> bytes: ...

    async def warm(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int: ...

    def stats(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class LLMClient(Protocol):
    """Chat completions with tools (OpenAI wire format)."""

    model: str

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
    ) -> LLMReply: ...

    def stats(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class ProviderUnavailable(RuntimeError):
    """A provider can't serve right now (not configured, down, out of quota) — try the next one."""


__all__ = ["LLMClient", "ProviderUnavailable", "STTEvent", "STTSession", "TTSEngine"]
