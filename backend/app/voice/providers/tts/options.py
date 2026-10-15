"""Text-to-speech knobs (voices, models, cache and breaker limits), read from ``.env``.

Keys and chains live in :mod:`app.voice.providers.settings`; this holds the
per-provider choices that rarely change but should not need a deploy to tune.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _settings_env_files


class TTSOptions(BaseSettings):
    model_config = SettingsConfigDict(env_file=_settings_env_files(), env_file_encoding="utf-8", extra="ignore")

    # --- cache -------------------------------------------------------------------------
    #: L1 (in-process) budget for hot lines.
    tts_hot_cache_mb: int = 32
    #: L3 (Supabase Storage) read budget; a slower tier is skipped, never waited on.
    tts_shared_cache_timeout_ms: int = 800

    # --- fallback chain ----------------------------------------------------------------
    #: Consecutive failures that take a provider out of the chain, and for how long.
    tts_breaker_errors: int = 2
    tts_breaker_seconds: float = 60.0
    #: One provider attempt for one line (then the next provider is tried).
    tts_attempt_timeout_seconds: float = 10.0

    # --- voices / models ---------------------------------------------------------------
    deepgram_tts_voice_female: str = "aura-2-thalia-en"
    deepgram_tts_voice_male: str = "aura-2-orion-en"
    gemini_tts_model: str = "gemini-3.8-flash-lite-tts"
    gemini_tts_fallback_model: str = "gemini-3.8-flash-tts"
    gemini_tts_voice_female: str = "Kore"
    gemini_tts_voice_male: str = "Charon"


@lru_cache
def get_tts_options() -> TTSOptions:
    return TTSOptions()


__all__ = ["TTSOptions", "get_tts_options"]
