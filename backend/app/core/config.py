"""Typed application settings loaded from environment variables and .env files.

Settings are layered from the repo-root ``.env`` and then ``backend/.env``
(later files win, real environment variables win over both). Only keys that
some module actually reads are declared here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: ``backend/`` — the directory that holds ``app/``.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
#: The repository root (parent of ``backend/``).
_REPO_ROOT = _BACKEND_ROOT.parent


def _settings_env_files() -> tuple[str, ...]:
    """The ``.env`` files settings are layered from, lowest precedence first."""
    return (str(_REPO_ROOT / ".env"), str(_BACKEND_ROOT / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BanglaBot Order Confirmation"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"
    log_level: str = "INFO"

    # --- Storage -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/banglabot"
    database_ssl: bool = False
    database_ssl_verify: bool = False
    database_pool_size: int = 5
    database_pool_max_overflow: int = 5
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---------------------------------------------------------------
    admin_username: str = "admin"
    admin_password: str = "admin@1234"
    admin_token_secret: str = Field(
        default="change-me-admin-token-secret",
        validation_alias=AliasChoices("ADMIN_TOKEN_SECRET", "JWT_SECRET"),
    )
    auto_seed_demo_data: bool = False

    # --- OpenAI: streaming STT + the call brain ------------------------------
    openai_api_key: str | None = None
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    openai_noise_reduction: str | None = "far_field"
    # Chat Completions + function tools need reasoning_effort "none" on
    # gpt-5.4-mini (also the lowest-latency setting for a phone line).
    openai_llm_model: str = "gpt-5.4-mini"
    openai_llm_reasoning_effort: str | None = "none"
    openai_llm_max_output_tokens: int = 300
    openai_llm_temperature: float | None = None
    # Server VAD for the transcription session (ms of trailing silence = end of turn).
    stt_vad_threshold: float = 0.5
    stt_vad_prefix_padding_ms: int = 300
    stt_vad_silence_duration_ms: int = 600

    # --- Azure Speech text-to-speech -----------------------------------------
    azure_speech_key: str | None = None
    azure_speech_region: str = "southeastasia"
    tts_voice_persona: str = "female"
    # SSML prosody rate, e.g. "-10%" to slow down; "0%" = the voice's default.
    tts_speaking_rate: str = "0%"
    # LRU cache of synthesized lines (a repeated sentence is never billed twice).
    tts_cache_dir: str = ".tts-cache"
    tts_cache_max_entries: int = 5000
    tts_cache_max_mb: int = 500

    # --- Call audio gates ------------------------------------------------------
    # μ-law RMS above which a caller frame counts as speech (silence watchdog).
    voice_speech_start_min_rms: int = 450
    # While the agent speaks, only SUSTAINED loud caller audio (this many ~20 ms
    # frames above the RMS gate) interrupts playback — the agent's own echo never does.
    voice_barge_in_min_rms: int = 1100
    voice_barge_in_min_frames: int = 20
    # Platform default cap on one confirmation call (merchant.max_call_seconds = 0).
    # Speak a one-word acknowledgement ("জি।" / "Okay.") the moment a caller turn
    # lands, masking the model + TTS latency of the real reply.
    voice_instant_ack: bool = True
    # Twilio answering-machine detection (async): a voicemail answer is hung up
    # on and the order stays callable (no_answer). Small per-call Twilio fee.
    voice_machine_detection: bool = True
    # Hang up when Twilio reports the call was forwarded to a DIFFERENT number
    # (divert service). Off by default: Bangladeshi carriers stamp forwarded_from
    # with the dialed number on ordinary answered calls, and answering-machine
    # detection already handles voicemail.
    voice_hangup_on_forwarded: bool = False
    voice_max_call_seconds: int = 240

    # --- Twilio ------------------------------------------------------------------
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = Field(
        default=None, validation_alias=AliasChoices("TWILIO_FROM_NUMBER", "TWILIO_PHONE_NUMBER")
    )
    # Public https origin Twilio can reach (status callbacks + media websocket).
    public_base_url: str | None = Field(
        default=None, validation_alias=AliasChoices("TWILIO_PUBLIC_BASE_URL", "PUBLIC_BASE_URL")
    )
    enforce_webhook_signatures: bool = False

    # --- Email (optional) ----------------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "BanglaBot"

    @field_validator("openai_api_key", "azure_speech_key", "public_base_url", "twilio_from_number", mode="before")
    @classmethod
    def blank_string_as_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
        if value == "":
            return None
        return value

    @property
    def twilio_public_base_url(self) -> str | None:
        """Alias kept for readers of the old name."""
        return self.public_base_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
