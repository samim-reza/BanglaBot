"""Shared behaviour of every TTS provider: voice resolution, caching, metering.

A provider subclasses :class:`CachedTTSEngine` and implements two things —
``resolve_voice`` (persona/language → its own voice id) and ``render`` (one
HTTP call → 8 kHz μ-law). Everything else (the L1/L2/L3 cache, in-flight
de-duplication, warming, stats) is here, so no provider can forget to cache.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

import structlog

from app.voice.languages import normalize_language
from app.voice.providers.base import ProviderUnavailable
from app.voice.tts_cache import TTSCache, normalize_text
from app.voice.tts_tiers import TieredTTSCache

logger = structlog.get_logger(__name__)

PERSONAS = ("female", "male")
DEFAULT_PERSONA = "female"


class TTSError(RuntimeError):
    """A line could not be synthesized."""


class TTSUnavailable(TTSError, ProviderUnavailable):
    """The provider can't serve now (auth, quota, down): skip it for a while."""


def normalize_persona(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in PERSONAS else DEFAULT_PERSONA


def unavailable_status(status: int) -> bool:
    """HTTP statuses that mean "stop asking this provider for now"."""
    return status in (401, 402, 403, 429)


class CachedTTSEngine:
    #: Provider name (cache keys, stats, logs).
    name = "base"
    #: Part of the cache key: what the stored bytes are.
    output_format = "ulaw8k"
    #: Two-letter languages this provider speaks; ``None`` = any.
    languages: frozenset[str] | None = None

    def __init__(self, *, cache: TieredTTSCache) -> None:
        self.cache = cache
        self.requests = 0
        self.chars = 0
        self.cached_chars = 0
        self.errors = 0
        self.synth_seconds = 0.0
        self.cache_hits: dict[str, int] = {"l1": 0, "l2": 0, "l3": 0, "inflight": 0}

    # ------------------------------------------------------------- per provider
    def supports(self, language: str | None) -> bool:
        return self.languages is None or normalize_language(language) in self.languages

    def resolve_voice(self, *, voice: str | None, persona: str | None, language: str) -> str:
        raise NotImplementedError

    async def render(self, text: str, *, voice: str, language: str) -> bytes:
        """One provider request → raw 8 kHz μ-law."""
        raise NotImplementedError

    def key_language(self, voice: str, language: str) -> str:
        return language

    def key_extra(self) -> str:
        return ""

    # ------------------------------------------------------------------ cache
    def cache_key(self, text: str, *, voice: str, language: str | None = None) -> str:
        lang = normalize_language(language)
        return TTSCache.make_key(
            provider=self.name,
            voice=voice,
            language=self.key_language(voice, lang),
            output_format=self.output_format,
            text=text,
            extra=self.key_extra(),
        )

    def key_for(self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None) -> str:
        lang = normalize_language(language)
        return self.cache_key(normalize_text(text), voice=self.resolve_voice(voice=voice, persona=persona, language=lang), language=lang)

    def is_cached(self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None) -> bool:
        return self.cache.contains(self.key_for(text, language=language, persona=persona, voice=voice))

    # ------------------------------------------------------------- synthesis
    async def synthesize_ex(
        self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None
    ) -> tuple[bytes, str]:
        """``(audio, source)`` where source is a cache tier, ``synth`` or ``inflight``."""
        text = normalize_text(text)
        if not text:
            return b"", "empty"
        lang = normalize_language(language)
        voice_id = self.resolve_voice(voice=voice, persona=persona, language=lang)
        key = self.cache_key(text, voice=voice_id, language=lang)

        async def produce() -> bytes:
            started = time.monotonic()
            try:
                audio = await self.render(text, voice=voice_id, language=lang)
            except Exception:
                self.errors += 1
                raise
            if not audio:
                self.errors += 1
                raise TTSError(f"{self.name}_tts_empty_audio")
            elapsed = time.monotonic() - started
            self.requests += 1
            self.chars += len(text)
            self.synth_seconds += elapsed
            await logger.adebug("tts_synthesized", provider=self.name, voice=voice_id, chars=len(text), ms=int(elapsed * 1000), bytes=len(audio))
            return audio

        audio, source = await self.cache.get_or_create(key, produce)
        if source in self.cache_hits:
            self.cache_hits[source] += 1
            self.cached_chars += len(text)
        return audio, source

    async def synthesize(
        self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None
    ) -> bytes:
        return (await self.synthesize_ex(text, language=language, persona=persona, voice=voice))[0]

    async def warm(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        """Pre-synthesize fixed lines; returns how many were not cached yet."""
        count = 0
        for line in lines:
            if not line or self.is_cached(line, language=language, persona=persona, voice=voice):
                continue
            try:
                _, source = await self.synthesize_ex(line, language=language, persona=persona, voice=voice)
            except TTSError as exc:
                await logger.awarning("tts_warm_failed", provider=self.name, error=str(exc), preview=str(line)[:60])
                continue
            count += source == "synth"
        return count

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "requests": self.requests,
            "chars": self.chars,
            "cached_chars": self.cached_chars,
            "cache_hits": dict(self.cache_hits),
            "errors": self.errors,
            "synth_seconds": round(self.synth_seconds, 3),
        }

    async def aclose(self) -> None:
        client = getattr(self, "_client", None)
        if client is not None:
            await client.aclose()


__all__ = [
    "DEFAULT_PERSONA",
    "PERSONAS",
    "CachedTTSEngine",
    "TTSError",
    "TTSUnavailable",
    "normalize_persona",
    "unavailable_status",
]
