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

    app_name: str = "BanglaBot Voice Agents"
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
    # Phone handsets are close-talking microphones: "near_field" suppresses line
    # noise without eating consonants the way the far-field profile does.
    openai_noise_reduction: str | None = "near_field"
    # Chat Completions + function tools need reasoning_effort "none" on
    # gpt-5.4-mini (also the lowest-latency setting for a phone line).
    openai_llm_model: str = "gpt-5.4-mini"
    openai_llm_reasoning_effort: str | None = "none"
    openai_llm_max_output_tokens: int = 300
    openai_llm_temperature: float | None = None
    # Extended prompt-cache retention ("24h") where the model supports it; empty =
    # the default in-memory retention (minutes). Unsupported values are dropped.
    openai_prompt_cache_retention: str | None = None
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
    # Inbound calls (booking a doctor, a technician, a viewing) run longer.
    voice_max_inbound_call_seconds: int = 480
    # Record inbound calls too (Twilio recording, started when the stream connects).
    voice_record_inbound: bool = True

    # --- Bulk dialer ("Call all" + scheduled auto-call) --------------------------
    # Calls a merchant may have live at once during a batch; the next order is
    # dialed as soon as one settles. Also bounded by what one server can run.
    bulk_call_max_concurrent: int = 3
    # Orders already dialed this many times are left out of batches (manual
    # calls are never limited).
    bulk_call_max_attempts: int = 3
    # Pause between two originations in a batch (Twilio rate-limits bursts).
    bulk_call_gap_seconds: float = 1.5
    # A scheduled auto-call found this far past its time (e.g. the server was
    # down) is skipped instead of dialing everyone at an unexpected hour.
    auto_call_max_late_minutes: int = 120

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

    # --- Inbound calls --------------------------------------------------------------
    # Account (username) that answers calls to a number no account has claimed —
    # handy in development with a single Twilio number. Empty = reject such calls.
    default_inbound_username: str | None = None
    # On startup, point TWILIO_FROM_NUMBER's voice webhook at {PUBLIC_BASE_URL}/twilio/inbound
    # (useful with ngrok, whose URL changes every run). Changes your Twilio number config.
    twilio_auto_configure_inbound: bool = False
    # Account whose website-chat widget the public website embeds as a live demo.
    demo_widget_username: str | None = "clinic"

    # --- SMS (Twilio Messaging) ------------------------------------------------------
    # Global switch; each account also has its own SMS settings.
    sms_enabled: bool = True
    # A Messaging Service SID (MG…) is preferred (sender pools, US A2P 10DLC);
    # otherwise SMS go out from TWILIO_SMS_FROM, falling back to TWILIO_FROM_NUMBER.
    twilio_messaging_service_sid: str | None = None
    twilio_sms_from: str | None = None
    # How often the reminder sender looks for upcoming appointments / visits.
    sms_reminder_interval_seconds: int = 300

    # --- Calendar sync -----------------------------------------------------------------
    # Google Calendar two-way sync (optional): an OAuth "Web application" client from
    # Google Cloud Console with the redirect URI below registered.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Default: {PUBLIC_BASE_URL or http://localhost:8000}/api/integrations/google/callback
    google_redirect_uri: str | None = None
    # How long imported busy times (iCal links / Google) are reused before refetching.
    calendar_busy_cache_seconds: int = 300
    # Secret used to encrypt integration credentials at rest (any long random string).
    encryption_secret: str | None = None

    # --- Chat channels -----------------------------------------------------------------
    # Facebook Messenger: the Meta app's secret (signs webhooks) and the verify token you
    # type into the app's webhook settings. WhatsApp uses the Twilio credentials above.
    meta_app_secret: str | None = None
    meta_verify_token: str | None = None
    meta_graph_version: str = "v21.0"

    # --- Jev (TypeSafe System One) -------------------------------------------------------
    # Optional fast yes/no + choice decisions on scripted steps the keyword matcher can't
    # settle; empty = off (the main model decides, as before).
    typesafe_api_key: str | None = None
    typesafe_model: str = "jev-latest"
    # Give up and let the main model decide after this long.
    typesafe_timeout_seconds: float = 0.8
    # Act on Jev only when it is at least this sure.
    typesafe_min_confidence: float = 0.85

    @field_validator(
        "openai_api_key", "azure_speech_key", "public_base_url", "twilio_from_number", "default_inbound_username",
        "openai_prompt_cache_retention", "twilio_messaging_service_sid", "twilio_sms_from", "google_client_id",
        "google_client_secret", "google_redirect_uri", "encryption_secret", "meta_app_secret", "meta_verify_token",
        "typesafe_api_key", mode="before",
    )
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
