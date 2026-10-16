"""Text-to-speech providers and the per-language engine the calls use.

``get_tts_for(language)`` returns a :class:`FallbackTTS` over the configured
providers of the chain (``TTS_CHAIN``); unknown or unconfigured names are
skipped. Provider engines are process-wide
singletons sharing one tiered cache (L1 memory, L2 disk, L3 Supabase Storage),
so a clip synthesized by any call is reused by every other one.
"""

from __future__ import annotations

from collections.abc import Sequence

from collections.abc import Callable
from typing import Any

import structlog

from app.core.config import get_settings
from app.voice.languages import normalize_language
from app.voice.providers.settings import get_provider_settings, parse_chain
from app.voice.providers.tts.base import CachedTTSEngine, TTSError
from app.voice.providers.tts.fallback import FallbackTTS
from app.voice.providers.tts.options import get_tts_options
from app.voice.tts_cache import TTSCache
from app.voice.tts_tiers import TieredTTSCache

logger = structlog.get_logger(__name__)

_cache: TieredTTSCache | None = None
_engines: dict[str, CachedTTSEngine | None] = {}
_chains: dict[tuple[str, ...], FallbackTTS] = {}


# ------------------------------------------------------------------ cache
def tts_cache() -> TieredTTSCache:
    """The process-wide tiered cache (built on first use)."""
    global _cache
    if _cache is None:
        settings = get_settings()
        options = get_tts_options()
        local = TTSCache(
            settings.tts_cache_dir,
            max_entries=settings.tts_cache_max_entries,
            max_bytes=int(settings.tts_cache_max_mb) * 1024 * 1024,
            hot_max_bytes=int(options.tts_hot_cache_mb) * 1024 * 1024,
        )
        _cache = TieredTTSCache(local, _shared_store(), shared_timeout=options.tts_shared_cache_timeout_ms / 1000)
    return _cache


def _shared_store():
    provider = get_provider_settings()
    if not (provider.supabase_url and provider.supabase_secret_key):
        return None
    from app.voice.tts_shared_cache import SupabaseTTSStore

    return SupabaseTTSStore(
        base_url=provider.supabase_url,
        secret_key=provider.supabase_secret_key,
        bucket=provider.tts_shared_cache_bucket,
        read_timeout=get_tts_options().tts_shared_cache_timeout_ms / 1000,
    )


# --------------------------------------------------------------- providers
def _azure(cache: TieredTTSCache) -> CachedTTSEngine | None:
    settings = get_settings()
    if not settings.azure_speech_key:
        return None
    from app.voice.providers.tts.azure import AzureTTS

    return AzureTTS(key=settings.azure_speech_key, region=settings.azure_speech_region, cache=cache, speaking_rate=settings.tts_speaking_rate)


def _deepgram(cache: TieredTTSCache) -> CachedTTSEngine | None:
    key = get_provider_settings().deepgram_api_key
    if not key:
        return None
    from app.voice.providers.tts.deepgram import DeepgramTTS

    options = get_tts_options()
    return DeepgramTTS(api_key=key, cache=cache, female_voice=options.deepgram_tts_voice_female, male_voice=options.deepgram_tts_voice_male)


def _gemini(cache: TieredTTSCache) -> CachedTTSEngine | None:
    key = get_provider_settings().gemini_api_key
    if not key:
        return None
    from app.voice.providers.tts.gemini import GeminiTTS

    options = get_tts_options()
    return GeminiTTS(
        api_key=key,
        cache=cache,
        model=options.gemini_tts_model,
        fallback_model=options.gemini_tts_fallback_model,
        female_voice=options.gemini_tts_voice_female,
        male_voice=options.gemini_tts_voice_male,
    )


def _edge(cache: TieredTTSCache) -> CachedTTSEngine | None:
    from app.voice.providers.tts.edge import EdgeTTS, edge_available

    return EdgeTTS(cache=cache, speaking_rate=get_settings().tts_speaking_rate) if edge_available() else None


def _local(cache: TieredTTSCache) -> CachedTTSEngine | None:
    provider = get_provider_settings()
    if not provider.speech_server_url:
        return None
    from app.voice.providers.tts.local import LocalTTS

    return LocalTTS(base_url=provider.speech_server_url, key=provider.speech_server_key, cache=cache)


FACTORIES: dict[str, Callable[[TieredTTSCache], CachedTTSEngine | None]] = {
    "azure": _azure,
    "deepgram": _deepgram,
    "gemini": _gemini,
    "edge": _edge,
    "local": _local,
}


def engine(name: str) -> CachedTTSEngine | None:
    """The shared engine for one provider, or ``None`` when it isn't configured."""
    if name not in _engines:
        factory = FACTORIES.get(name)
        if factory is None:
            logger.warning("tts_unknown_provider", provider=name)
            _engines[name] = None
        else:
            _engines[name] = factory(tts_cache())
    return _engines[name]


# ------------------------------------------------------------------ chains
def tts_chain_for(language: str | None) -> list[str]:
    """The platform TTS chain (one chain; ``language`` kept for the callers' plumbing)."""
    return parse_chain(get_provider_settings().tts_chain)


def configured_providers(language: str | None, chain: Sequence[str] | None = None) -> list[str]:
    """The chain's configured providers; ``chain`` = an account's admin override (falls back to the platform chain)."""
    if chain:
        names = [name for name in chain if engine(name) is not None]
        if names:
            return names
    return [name for name in tts_chain_for(language) if engine(name) is not None]


def tts_available(language: str | None = None) -> bool:
    """Some provider in the language's chain is configured (no network)."""
    return bool(configured_providers(language))


def get_tts_for(language: str | None, chain: Sequence[str] | None = None) -> FallbackTTS:
    """The fallback engine for ``language`` (cached per resolved chain; ``chain`` = account override)."""
    names = tuple(configured_providers(language, chain))
    if not names:
        raise TTSError(f"no TTS provider configured for {normalize_language(language)!r} (chain {tts_chain_for(language)})")
    found = _chains.get(names)
    if found is None:
        options = get_tts_options()
        found = FallbackTTS(
            [engine(name) for name in names],  # type: ignore[misc]
            cache=tts_cache(),
            error_threshold=options.tts_breaker_errors,
            cooldown_seconds=options.tts_breaker_seconds,
            attempt_timeout=options.tts_attempt_timeout_seconds,
        )
        _chains[names] = found
        logger.info("tts_chain_ready", language=normalize_language(language), chain=list(names))
    return found


def tts_stats() -> dict[str, Any]:
    """Every chain built so far plus the cache tiers (admin / finance view)."""
    return {
        "chains": {",".join(names): chain.stats()["providers"] for names, chain in _chains.items()},
        "cache": tts_cache().stats() if _cache is not None else None,
    }


# --------------------------------------------------------------- lifecycle
def cache_built() -> bool:
    return _cache is not None


def flush_caches() -> None:
    if _cache is not None:
        _cache.flush()


async def aclose_all() -> None:
    for item in list(_engines.values()):
        if item is not None:
            try:
                await item.aclose()
            except Exception:  # noqa: BLE001 — shutdown is best effort
                pass
    if _cache is not None:
        await _cache.aclose()
    reset_registry()


def reset_registry(cache: TieredTTSCache | None = None) -> None:
    """Drop the singletons (tests; optionally install a prepared cache)."""
    global _cache
    _engines.clear()
    _chains.clear()
    _cache = cache


__all__ = [
    "FACTORIES",
    "FallbackTTS",
    "TTSError",
    "aclose_all",
    "cache_built",
    "configured_providers",
    "engine",
    "flush_caches",
    "get_tts_for",
    "reset_registry",
    "tts_available",
    "tts_cache",
    "tts_chain_for",
    "tts_stats",
]
