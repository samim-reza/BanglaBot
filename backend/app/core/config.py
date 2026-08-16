"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BanglaBot"
    environment: str = "development"

    # Supabase Postgres (session pooler)
    database_url: str = ""

    # Redis cache (login rate limiting, hot-read caching). Empty or unreachable
    # falls back to a per-process in-memory cache — never fatal.
    redis_url: str = "redis://localhost:6379/0"

    # Comma-separated browser origins allowed for CORS. In dev the Vite proxy
    # makes API calls same-origin, so this only matters for direct-origin setups.
    frontend_origin: str = "http://localhost:5173"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Public URL (ngrok in local dev) used for Twilio webhooks
    public_base_url: str = ""

    # OpenAI (LLM + STT)
    openai_api_key: str = ""
    openai_llm_model: str = "gpt-5.4-mini"
    openai_stt_model: str = "gpt-4o-mini-transcribe"

    # TTS: elevenlabs (default) | google (Chirp 3 HD) | gemini (Gemini TTS, plain API key)
    tts_provider: str = "elevenlabs"
    gemini_api_key: str = ""
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_tts_voice: str = "Kore"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_v3"
    google_credentials_path: str = ""
    google_tts_voice: str = "bn-IN-Chirp3-HD-Aoede"

    # Call behavior
    max_call_seconds: int = 240

    # Reject Twilio webhooks whose X-Twilio-Signature doesn't verify.
    twilio_validate_webhooks: bool = True

    # Twilio <Say> voice for static (keypad) calls.
    twilio_say_voice: str = "Google.bn-IN-Wavenet-A"

    # Bootstrap platform admin (created if missing)
    admin_username: str = "admin"
    admin_password: str = "admin123"


@lru_cache
def get_settings() -> Settings:
    return Settings()
