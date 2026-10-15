"""One TTS engine over an ordered chain of providers, with a circuit breaker.

Each line goes to the first provider that speaks the language and is not
"open" (benched). A provider that fails ``error_threshold`` times in a row —
or once with an auth/quota error — is benched for ``cooldown_seconds``; when
every provider is benched they are all tried anyway (half-open), so a call
never goes silent just because the breaker is pessimistic.

Every served line is recorded per provider (lines, chars, cache hits) for the
finance view; ``recent`` keeps the last few hundred for debugging.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import structlog

from app.voice.providers.spend import over_cap
from app.voice.providers.base import ProviderUnavailable
from app.voice.providers.tts.base import CachedTTSEngine, TTSError
from app.voice.tts_cache import normalize_text
from app.voice.tts_tiers import TieredTTSCache

logger = structlog.get_logger(__name__)


@dataclass
class _Health:
    consecutive_errors: int = 0
    open_until: float = 0.0
    trips: int = 0
    errors: int = 0
    lines: int = 0
    chars: int = 0
    cached_lines: int = 0
    last_error: str = ""


class FallbackTTS:
    name = "fallback"

    def __init__(
        self,
        engines: Iterable[CachedTTSEngine],
        *,
        cache: TieredTTSCache,
        error_threshold: int = 2,
        cooldown_seconds: float = 60.0,
        attempt_timeout: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.engines = list(engines)
        if not self.engines:
            raise TTSError("no TTS provider configured")
        self.cache = cache
        self.error_threshold = max(1, int(error_threshold))
        self.cooldown_seconds = float(cooldown_seconds)
        self.attempt_timeout = float(attempt_timeout)
        self._clock = clock
        self._health: dict[str, _Health] = {engine.name: _Health() for engine in self.engines}
        self.fallbacks = 0
        self.failures = 0
        self.recent: deque[dict[str, Any]] = deque(maxlen=200)

    @property
    def chain(self) -> list[str]:
        return [engine.name for engine in self.engines]

    # ---------------------------------------------------------------- routing
    def _candidates(self, language: str | None) -> list[CachedTTSEngine]:
        speaking = [engine for engine in self.engines if engine.supports(language)]
        now = self._clock()
        closed = [engine for engine in speaking if self._health[engine.name].open_until <= now]
        affordable = [engine for engine in closed if not over_cap(engine.name)]
        return affordable or closed or speaking

    def is_open(self, name: str) -> bool:
        health = self._health.get(name)
        return bool(health and health.open_until > self._clock())

    def _succeeded(self, engine: CachedTTSEngine, text: str, source: str, *, fell_back: bool) -> None:
        health = self._health[engine.name]
        health.consecutive_errors = 0
        health.open_until = 0.0
        health.lines += 1
        cached = source not in ("synth", "empty")
        if cached:
            health.cached_lines += 1
        else:
            health.chars += len(text)
        if fell_back:
            self.fallbacks += 1
        self.recent.append({"provider": engine.name, "chars": len(text), "source": source, "at": time.time()})

    def _failed(self, engine: CachedTTSEngine, exc: BaseException) -> None:
        health = self._health[engine.name]
        health.errors += 1
        health.consecutive_errors += 1
        health.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        if isinstance(exc, ProviderUnavailable) or health.consecutive_errors >= self.error_threshold:
            health.open_until = self._clock() + self.cooldown_seconds
            health.consecutive_errors = 0
            health.trips += 1
            logger.warning("tts_provider_benched", provider=engine.name, seconds=self.cooldown_seconds, error=health.last_error)

    # ------------------------------------------------------------- synthesis
    async def synthesize_ex(
        self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None
    ) -> tuple[bytes, str, str]:
        """``(audio, provider, source)`` for one line."""
        text = normalize_text(text)
        if not text:
            return b"", "", "empty"
        candidates = self._candidates(language)
        if not candidates:
            raise TTSError(f"no TTS provider in {self.chain} speaks {language!r}")
        # The provider this language would normally use (benched or not): anything
        # else serving the line is a fallback, for the finance view and the logs.
        preferred = next(engine for engine in self.engines if engine.supports(language))
        errors: list[str] = []
        for engine in candidates:
            try:
                audio, source = await asyncio.wait_for(
                    engine.synthesize_ex(text, language=language, persona=persona, voice=voice),
                    timeout=self.attempt_timeout,
                )
            except Exception as exc:  # noqa: BLE001 — any provider failure falls through
                self._failed(engine, exc)
                errors.append(f"{engine.name}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            fell_back = engine is not preferred
            self._succeeded(engine, text, source, fell_back=fell_back)
            if fell_back and errors:
                await logger.ainfo("tts_fallback_served", provider=engine.name, failed=[e.split(":")[0] for e in errors])
            return audio, engine.name, source
        self.failures += 1
        raise TTSError("all TTS providers failed: " + "; ".join(errors))

    async def synthesize(
        self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None
    ) -> bytes:
        return (await self.synthesize_ex(text, language=language, persona=persona, voice=voice))[0]

    def is_cached(self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None) -> bool:
        """Whether the provider that would serve this line has it locally (L1/L2)."""
        candidates = self._candidates(language)
        return bool(candidates) and candidates[0].is_cached(text, language=language, persona=persona, voice=voice)

    async def warm(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        """Pre-synthesize fixed lines with the provider that will speak them."""
        count = 0
        for line in lines:
            if not line or self.is_cached(line, language=language, persona=persona, voice=voice):
                continue
            try:
                _, _, source = await self.synthesize_ex(line, language=language, persona=persona, voice=voice)
            except TTSError as exc:
                await logger.awarning("tts_warm_failed", error=str(exc)[:300], preview=str(line)[:60])
                continue
            count += source == "synth"
        return count

    # ------------------------------------------------------------------ pins
    def cache_keys(self, text: str, *, language: str | None = None, persona: str | None = None, voice: str | None = None) -> list[str]:
        """This line's key for every provider in the chain that speaks the language."""
        return [
            engine.key_for(text, language=language, persona=persona, voice=voice)
            for engine in self.engines
            if engine.supports(language)
        ]

    def pin_lines(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        """Never evict these lines, whichever provider ends up speaking them."""
        keys = [key for line in lines if line for key in self.cache_keys(line, language=language, persona=persona, voice=voice)]
        return self.cache.pin(keys)

    def unpin_lines(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        keys = [key for line in lines if line for key in self.cache_keys(line, language=language, persona=persona, voice=voice)]
        return self.cache.unpin(keys)

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict[str, Any]:
        now = self._clock()
        providers: dict[str, Any] = {}
        for engine in self.engines:
            health = self._health[engine.name]
            providers[engine.name] = {
                **engine.stats(),
                "served_lines": health.lines,
                "served_chars": health.chars,
                "served_cached_lines": health.cached_lines,
                "fallback_errors": health.errors,
                "benched": health.open_until > now,
                "benched_for": round(max(0.0, health.open_until - now), 1),
                "trips": health.trips,
                "last_error": health.last_error,
            }
        return {"chain": self.chain, "providers": providers, "fallbacks": self.fallbacks, "failures": self.failures, "cache": self.cache.stats()}

    async def aclose(self) -> None:
        """Engines are shared process-wide; the registry closes them."""
        return None


__all__ = ["FallbackTTS"]
