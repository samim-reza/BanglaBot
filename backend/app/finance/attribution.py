"""Which provider most likely served a call when its usage report doesn't say.

Used only as a fallback (meter lines get ``meta.estimated``): the first
configured entry of the platform's LLM / STT / TTS chain for the language.
Never raises — a hard default is returned when the provider layer can't be read.
"""

from __future__ import annotations

from typing import Any

from app.finance.pricebook_defaults import TTS_SKUS

DEFAULT_LLM = ("groq", "openai/gpt-oss-120b")
DEFAULT_STT = ("deepgram", "nova-3")
DEFAULT_TTS = ("azure", "neural-tts")


def default_llm(merchant: Any | None = None) -> tuple[str, str]:
    try:
        from app.voice.providers.llm.factory import chain_for

        links = chain_for(merchant)
        if links:
            return links[0].provider, links[0].model
    except Exception:  # noqa: BLE001 — metering fallback only
        pass
    return DEFAULT_LLM


def stt_model(provider: str) -> str:
    if provider == "deepgram":
        return "nova-3"
    if provider == "groq":
        return "whisper-large-v3-turbo"
    if provider == "openai":
        try:
            from app.core.config import get_settings

            return str(get_settings().openai_transcription_model or "gpt-4o-mini-transcribe")
        except Exception:  # noqa: BLE001
            return "gpt-4o-mini-transcribe"
    return provider


def default_stt(language: str | None = None) -> tuple[str, str]:
    try:
        from app.voice.providers.stt import configured_providers

        names = configured_providers(language)
        if names:
            return names[0], stt_model(names[0])
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_STT


def tts_sku(provider: str) -> str:
    return TTS_SKUS.get(provider, provider)


def default_tts(language: str | None = None) -> tuple[str, str]:
    try:
        from app.voice.providers.tts import configured_providers

        names = configured_providers(language)
        if names:
            return names[0], tts_sku(names[0])
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_TTS


__all__ = ["DEFAULT_LLM", "DEFAULT_STT", "DEFAULT_TTS", "default_llm", "default_stt", "default_tts", "stt_model", "tts_sku"]
