"""The e2e run's environment: which database it may wipe, and the settings that keep it hermetic."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ADMIN_USERNAME = "e2e-root"
ADMIN_PASSWORD = "Root-Pass-e2e-7193!"

_BLANK = (
    "REDIS_URL", "TELNYX_API_KEY", "TELNYX_TEXML_APP_ID", "TELNYX_FROM_NUMBER", "TELNYX_PHONE_NUMBER", "TELNYX_PUBLIC_KEY",
    "TELNYX_ACCOUNT_SID", "TELNYX_MESSAGING_PROFILE_ID", "TELNYX_SMS_FROM", "TELNYX_WEBHOOK_SECRET", "OPENAI_API_KEY",
    "GROQ_API_KEY", "GEMINI_API_KEY", "DEEPGRAM_API_KEY", "OPENROUTER_API_KEY", "AZURE_SPEECH_KEY", "SPEECH_SERVER_URL",
    "SPEECH_SERVER_KEY", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI", "META_APP_SECRET", "META_VERIFY_TOKEN",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TYPESAFE_API_KEY", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD",
    "ADMIN_TOKEN_SECRET_PREVIOUS", "ENCRYPTION_SECRET_PREVIOUS", "JWT_SECRET", "PROVIDER_DAILY_CAPS_USD",
)


def check_target(url: str) -> tuple[str, int]:
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    host, name = str(parsed.host or ""), str(parsed.database or "")
    if host not in ("127.0.0.1", "localhost", "::1") or not any(tag in name for tag in ("e2e", "test")):
        raise pytest.UsageError(f"E2E_DATABASE_URL must be a loopback throwaway database named *e2e*/*test* (got {host}/{name}): it is wiped")
    return host, int(parsed.port or 5432)


def configure_environment(url: str) -> None:
    """Environment variables win over .env; then the .env files are switched off entirely."""
    if "app.core.config" in sys.modules:
        raise pytest.UsageError("run the e2e suite on its own (pytest tests/e2e): app settings were already loaded")
    os.environ.update({key: "" for key in _BLANK})
    os.environ.update(
        {
            "DATABASE_URL": url, "DATABASE_SSL": "false", "ENVIRONMENT": "test", "LOG_LEVEL": "WARNING",
            "TELNYX_AUTO_CONFIGURE_INBOUND": "false", "ENFORCE_WEBHOOK_SIGNATURES": "false", "SMS_ENABLED": "false",
            "PAYMENT_PROVIDER": "dummy", "PUBLIC_BASE_URL": "http://testserver", "FRONTEND_ORIGIN": "http://portal.test",
            "ADMIN_USERNAME": ADMIN_USERNAME, "ADMIN_PASSWORD": ADMIN_PASSWORD,
            "ADMIN_TOKEN_SECRET": "e2e-admin-token-secret-0123456789abcdef-xyz",
            "ENCRYPTION_SECRET": "e2e-encryption-secret-0123456789abcdef-xyz",
            "TRUSTED_PROXY_HOPS": "1", "TTS_CACHE_DIR": tempfile.mkdtemp(prefix="callisa-e2e-tts-"),
            "DATABASE_POOL_SIZE": "10", "DATABASE_POOL_MAX_OVERFLOW": "10",
        }
    )
    from app.core import config

    config._settings_env_files = lambda: ()  # settings classes defined from now on read no .env
    config.Settings.model_config["env_file"] = None
    config.get_settings.cache_clear()
