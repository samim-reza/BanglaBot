"""Speech-to-text providers and the chain walk that opens one per call.

``open_stt(language=...)`` tries the language's chain (``STT_CHAIN`` /
``STT_CHAIN_BN``) in order: providers without a key (or without a speech
server URL) are skipped, a paused provider (recent auth/quota/connect failure)
is skipped, the local server must answer a cached health probe, and the first
session that connects serves the call. If it dies mid-call the bridge simply
calls ``open_stt`` again and lands on the next healthy provider.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import structlog

from app.voice.providers.spend import over_cap
from app.voice.languages import BANGLA, normalize_language
from app.voice.providers.base import ProviderUnavailable, STTSession
from app.voice.providers.settings import get_provider_settings, parse_chain
from app.voice.providers.stt import health
from app.voice.providers.stt.options import get_stt_options

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class STTProvider:
    name: str
    configured: Callable[[], bool]
    #: (language, prompt, keyterms) → an unconnected session.
    build: Callable[[str, str, list[str]], STTSession]


def _openai(language: str, prompt: str, keyterms: list[str]) -> STTSession:
    from app.voice.providers.stt import openai

    return openai.create(language=language, prompt=prompt, keyterms=keyterms)  # type: ignore[return-value]


def _openai_configured() -> bool:
    from app.voice.providers.stt import openai

    return openai.configured()


def _deepgram(language: str, prompt: str, keyterms: list[str]) -> STTSession:
    from app.voice.providers.stt.deepgram import DeepgramSTT

    options = get_stt_options()
    return DeepgramSTT(
        api_key=str(get_provider_settings().deepgram_api_key or ""),
        language=language,
        keyterms=keyterms,
        model=options.deepgram_stt_model,
        endpointing_ms=options.deepgram_endpointing_ms,
        utterance_end_ms=options.deepgram_utterance_end_ms,
        max_keyterms=options.deepgram_max_keyterms,
        end_silence_ms=options.stt_end_silence_ms,
    )


def _groq(language: str, prompt: str, keyterms: list[str]) -> STTSession:
    from app.voice.providers.stt.groq import GroqWhisperSTT
    from app.voice.providers.stt.vad import EnergyVAD

    options = get_stt_options()
    return GroqWhisperSTT(
        api_key=str(get_provider_settings().groq_api_key or ""),
        language=language,
        prompt=prompt,
        model=options.groq_stt_model,
        noise_logprob=options.groq_noise_logprob,
        vad=EnergyVAD(end_silence_ms=options.stt_end_silence_ms),
    )


def _local(language: str, prompt: str, keyterms: list[str]) -> STTSession:
    from app.voice.providers.stt.local import LocalSTT

    settings = get_provider_settings()
    return LocalSTT(
        base_url=str(settings.speech_server_url or ""),
        key=settings.speech_server_key,
        language=language,
        prompt=prompt,
        keyterms=keyterms,
        silence_ms=get_stt_options().stt_end_silence_ms,
    )


PROVIDERS: dict[str, STTProvider] = {
    "local": STTProvider("local", lambda: bool(get_provider_settings().speech_server_url), _local),
    "deepgram": STTProvider("deepgram", lambda: bool(get_provider_settings().deepgram_api_key), _deepgram),
    "groq": STTProvider("groq", lambda: bool(get_provider_settings().groq_api_key), _groq),
    "openai": STTProvider("openai", _openai_configured, _openai),
}


def stt_chain_for(language: str | None) -> list[str]:
    settings = get_provider_settings()
    raw = settings.stt_chain_bn if normalize_language(language) == BANGLA else settings.stt_chain
    return parse_chain(raw)


def configured_providers(language: str | None, chain: Sequence[str] | None = None) -> list[str]:
    names = list(chain) if chain is not None else stt_chain_for(language)
    return [name for name in names if name in PROVIDERS and PROVIDERS[name].configured()]


def stt_available(language: str | None = None) -> bool:
    """Some provider in the language's chain has its key / URL (no network)."""
    return bool(configured_providers(language))


async def _local_ready() -> bool:
    settings = get_provider_settings()
    return await health.speech_server_healthy(settings.speech_server_url, settings.speech_server_key)


async def _discard(session: STTSession) -> None:
    try:
        await session.close()
    except Exception:  # noqa: BLE001
        pass


async def open_stt(
    *,
    language: str,
    prompt: str = "",
    keyterms: Sequence[str] = (),
    chain: Sequence[str] | None = None,
) -> STTSession:
    """A connected session from the first healthy provider of the chain."""
    lang = normalize_language(language)
    options = get_stt_options()
    terms = [str(term) for term in keyterms if term]
    skipped: list[str] = []
    names = configured_providers(lang, chain)
    # Providers over today's spend cap go last (still better than no transcription at all).
    names = [n for n in names if not over_cap(n)] + [n for n in names if over_cap(n)]
    for name in names:
        if health.is_down(name):
            skipped.append(f"{name}:paused")
            continue
        if name == "local" and not await _local_ready():
            skipped.append("local:unhealthy")
            continue
        session = PROVIDERS[name].build(lang, prompt, terms)
        try:
            await asyncio.wait_for(session.connect(), timeout=options.stt_connect_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — any connect failure falls through
            await _discard(session)
            health.mark_down(name, options.stt_connect_failure_pause_seconds, reason=f"connect: {type(exc).__name__}: {exc}")
            skipped.append(f"{name}:{type(exc).__name__}")
            continue
        await logger.ainfo("stt_provider_selected", provider=name, language=lang, skipped=skipped)
        return session
    raise ProviderUnavailable(f"no STT provider could serve {lang!r} (chain {list(chain or stt_chain_for(lang))}, skipped {skipped})")


__all__ = ["PROVIDERS", "STTProvider", "configured_providers", "open_stt", "stt_available", "stt_chain_for"]
