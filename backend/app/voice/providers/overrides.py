"""An account's admin-set provider chains (``merchants.provider_settings``) for STT / TTS / LLM."""

from __future__ import annotations

from typing import Any

from app.voice.providers.settings import parse_chain


def provider_override(merchant: Any, key: str) -> list[str] | None:
    """``key`` = "stt_chain" | "tts_chain" | "llm_chain" → the override list, or ``None`` (platform default)."""
    settings = getattr(merchant, "provider_settings", None)
    if not isinstance(settings, dict):
        return None
    names = parse_chain(settings.get(key))
    return names or None


__all__ = ["provider_override"]
