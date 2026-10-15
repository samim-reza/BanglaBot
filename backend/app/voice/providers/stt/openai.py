"""OpenAI Realtime transcription (paid) as an STT provider.

The session itself is :class:`app.voice.stt.TranscriptionStream` (server VAD,
``gpt-4o-mini-transcribe``); this module only builds it from the app settings.
OpenAI has no keyterm list — names reach it through the prompt.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.config import get_settings
from app.voice.stt import TranscriptionStream


def configured() -> bool:
    return bool(get_settings().openai_api_key)


def prompt_with_keyterms(prompt: str, keyterms: Sequence[str], *, limit: int = 900) -> str:
    """Append names the prompt doesn't mention yet (the bridge usually already did)."""
    parts = [prompt.strip()] if prompt.strip() else []
    for term in keyterms:
        if term and term not in prompt:
            parts.append(f"{term}.")
    return " ".join(parts)[:limit].strip()


def create(*, language: str | None, prompt: str = "", keyterms: Sequence[str] = ()) -> TranscriptionStream:
    settings = get_settings()
    return TranscriptionStream(
        api_key=str(settings.openai_api_key or ""),
        model=settings.openai_transcription_model,
        language=language,
        prompt=prompt_with_keyterms(prompt, keyterms),
        vad_threshold=settings.stt_vad_threshold,
        vad_prefix_padding_ms=settings.stt_vad_prefix_padding_ms,
        vad_silence_duration_ms=settings.stt_vad_silence_duration_ms,
        noise_reduction=settings.openai_noise_reduction,
    )


__all__ = ["configured", "create", "prompt_with_keyterms"]
