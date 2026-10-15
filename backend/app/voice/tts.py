"""Compatibility layer over :mod:`app.voice.providers.tts`.

The phone line's TTS used to be one hard-wired Azure client; it is now a
per-language fallback chain of providers sharing a tiered cache. Callers that
know the language should use ``get_tts_for(language)``. ``get_tts()`` keeps
working for the rest: it returns a router that sends every line to the chain
of the language it is spoken in.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.voice.providers.tts import aclose_all, cache_built, get_tts_for, tts_available, tts_cache, tts_stats
from app.voice.providers.tts.azure import (
    ENGLISH_ACCENTS,
    OUTPUT_FORMAT,
    PROVIDER,
    VOICE_PERSONAS,
    voice_for,
)
from app.voice.providers.tts.azure import AzureTTS as AzureSpeechTTS
from app.voice.providers.tts.base import DEFAULT_PERSONA, TTSError, TTSUnavailable, normalize_persona


class LanguageRoutedTTS:
    """``TTSEngine`` that dispatches each call to ``get_tts_for(language)``."""

    name = "routed"

    @property
    def cache(self):
        return tts_cache()

    async def synthesize(
        self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None
    ) -> bytes:
        return await get_tts_for(language).synthesize(text, language=language, persona=persona, voice=voice)

    async def warm(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        return await get_tts_for(language).warm(lines, language=language, persona=persona, voice=voice)

    def is_cached(self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None) -> bool:
        return get_tts_for(language).is_cached(text, language=language, persona=persona, voice=voice)

    def pin_lines(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        return get_tts_for(language).pin_lines(lines, language=language, persona=persona, voice=voice)

    def stats(self) -> dict[str, Any]:
        return tts_stats()

    async def aclose(self) -> None:
        await aclose_all()


_router = LanguageRoutedTTS()


def get_tts() -> LanguageRoutedTTS:
    """Process-wide TTS (routes by language); raises ``TTSError`` when nothing is configured."""
    if not tts_configured():
        raise TTSError("no TTS provider is configured (AZURE_SPEECH_KEY, DEEPGRAM_API_KEY, GEMINI_API_KEY, edge-tts…)")
    return _router


def tts_configured(language: str | None = None) -> bool:
    return tts_available(language)


def __getattr__(name: str) -> Any:
    # ``from app.voice.tts import _tts`` (shutdown flush in main.py): the router
    # once the shared cache exists, so ``_tts.cache.flush()`` still works.
    if name == "_tts":
        return _router if cache_built() else None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DEFAULT_PERSONA",
    "ENGLISH_ACCENTS",
    "OUTPUT_FORMAT",
    "PROVIDER",
    "VOICE_PERSONAS",
    "AzureSpeechTTS",
    "LanguageRoutedTTS",
    "TTSError",
    "TTSUnavailable",
    "get_tts",
    "get_tts_for",
    "normalize_persona",
    "tts_configured",
    "voice_for",
]
