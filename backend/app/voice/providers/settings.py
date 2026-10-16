"""Provider keys and chains, loaded from the same ``.env`` files as the app settings.

Kept apart from :mod:`app.core.config` so the provider layer owns its knobs.
A chain is a comma-separated, ordered list of provider names; the first one
that is configured and healthy serves the call.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _settings_env_files


class ProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_settings_env_files(), env_file_encoding="utf-8", extra="ignore")

    # --- keys (empty = provider off) ---------------------------------------------------
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    deepgram_api_key: str | None = None

    # --- LLM ---------------------------------------------------------------------------
    #: provider:model entries, tried in order. "openai" is used only when OPENAI_API_KEY is set
    #: and LLM_ALLOW_PAID is true.
    #: Measured 2026-10-16 with a tool call: gpt-oss-120b ≈ 0.8 s, gpt-oss-20b / qwen ≈ 0.5 s,
    #: gemini-3.1-flash-lite ≈ 1.0 s. Groq limits are per model, so its models back each other up.
    llm_chain: str = (
        "groq:openai/gpt-oss-120b,groq:openai/gpt-oss-20b,gemini:gemini-3.1-flash-lite,"
        "groq:qwen/qwen3.8-27b,gemini:gemini-3.8-flash,openai:gpt-5.4-mini"
    )
    llm_allow_paid: bool = False
    llm_timeout_seconds: float = 20.0
    #: One link's timeout on a live call (the next link is tried after it); chat keeps the one above.
    llm_voice_timeout_seconds: float = 8.0
    llm_max_output_tokens: int = 300
    #: compact | cached | auto (auto = cached for OpenAI, compact for free tiers).
    llm_prompt_profile: str = "auto"

    # --- STT / TTS chains (names resolved by providers/stt and providers/tts) -------------
    stt_chain: str = "local,deepgram,groq,openai"
    tts_chain: str = "local,deepgram,azure,gemini,edge"

    # --- local open-source speech server (speech/, laptop GPU) ---------------------------
    speech_server_url: str | None = None
    speech_server_key: str | None = None

    # --- shared TTS cache tier (Supabase Storage) ----------------------------------------
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    tts_shared_cache_bucket: str = "tts-cache"

    @field_validator(
        "groq_api_key", "gemini_api_key", "openrouter_api_key", "deepgram_api_key", "speech_server_url",
        "speech_server_key", "supabase_url", "supabase_secret_key", mode="before",
    )
    @classmethod
    def _blank_as_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value or None


def parse_chain(raw: str | None) -> list[str]:
    """``"a, b,,c"`` → ``["a", "b", "c"]`` (order kept, duplicates dropped)."""
    seen: list[str] = []
    for part in str(raw or "").split(","):
        name = part.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


@lru_cache
def get_provider_settings() -> ProviderSettings:
    return ProviderSettings()


__all__ = ["ProviderSettings", "get_provider_settings", "parse_chain"]
