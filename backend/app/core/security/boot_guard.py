"""Refuse to run production with development secrets.

``check_settings`` lists what is unsafe; ``enforce`` raises in production (the
app's startup fails, so the deploy never goes live) and only warns elsewhere.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.security.policy import is_weak

DEFAULT_TOKEN_SECRETS = frozenset({"change-me-admin-token-secret", "changeme", "change-me", "secret", "dev"})
DEFAULT_ADMIN_PASSWORDS = frozenset({"admin@1234", "admin", "password", "changeme", "admin123"})
MIN_SECRET_CHARS = 32


class InsecureConfiguration(RuntimeError):
    pass


def is_production(settings: Any) -> bool:
    return str(getattr(settings, "environment", "") or "").strip().lower() in ("production", "prod")


def webhook_signatures_enforced(settings: Any) -> bool:
    """Unsigned webhook URLs refused: ``ENFORCE_WEBHOOK_SIGNATURES``, or production when unset."""
    explicit = getattr(settings, "enforce_webhook_signatures", None)
    return is_production(settings) if explicit is None else bool(explicit)


def api_docs_enabled(settings: Any) -> bool:
    """FastAPI's /docs and /openapi.json: ``EXPOSE_API_DOCS``, or everywhere but production when unset."""
    explicit = getattr(settings, "expose_api_docs", None)
    return not is_production(settings) if explicit is None else bool(explicit)


def advisories(settings: Any) -> list[str]:
    """Production settings that are allowed but weaken a control (logged at startup)."""
    if not is_production(settings):
        return []
    notes: list[str] = []
    if not webhook_signatures_enforced(settings):
        notes.append("ENFORCE_WEBHOOK_SIGNATURES=false: unsigned Telnyx / Twilio webhooks are accepted")
    if api_docs_enabled(settings):
        notes.append("EXPOSE_API_DOCS=true: /docs and /openapi.json are public")
    try:
        from app.services.payments.config import get_payment_settings

        payments = get_payment_settings()
        if payments.payment_provider != "stripe" or not payments.stripe_ready():
            notes.append("payments use the dummy pay page: whoever holds a pay link can mark it paid without paying")
    except Exception:  # noqa: BLE001 — advisory only
        pass
    return notes


def check_settings(settings: Any) -> list[str]:
    problems: list[str] = []
    secret = str(settings.admin_token_secret or "")
    if secret in DEFAULT_TOKEN_SECRETS or secret.startswith("change-me") or len(secret) < MIN_SECRET_CHARS:
        problems.append(f"ADMIN_TOKEN_SECRET is a default or shorter than {MIN_SECRET_CHARS} characters")
    password = str(settings.admin_password or "")
    if password in DEFAULT_ADMIN_PASSWORDS or is_weak(password, username=str(settings.admin_username or "")):
        problems.append("ADMIN_PASSWORD is a default or too weak (10+ characters, not common, not the username)")
    if not settings.encryption_secret:
        problems.append("ENCRYPTION_SECRET is not set")
    elif len(settings.encryption_secret) < MIN_SECRET_CHARS:
        problems.append(f"ENCRYPTION_SECRET is shorter than {MIN_SECRET_CHARS} characters")
    webhook_secret = getattr(settings, "telnyx_webhook_secret", None)
    if webhook_secret and len(webhook_secret) < MIN_SECRET_CHARS:
        problems.append(f"TELNYX_WEBHOOK_SECRET is shorter than {MIN_SECRET_CHARS} characters")
    if is_production(settings) and getattr(settings, "outbound_allow_private", False):
        problems.append("OUTBOUND_ALLOW_PRIVATE must be off in production (owner URLs could reach internal hosts)")
    return problems


def enforce(settings: Any) -> list[str]:
    """Raise ``InsecureConfiguration`` in production; log a warning otherwise."""
    problems = check_settings(settings)
    for note in advisories(settings):
        structlog.get_logger(__name__).warning("weakened_production_control", note=note)
    if not problems:
        return problems
    if is_production(settings):
        raise InsecureConfiguration("Refusing to start in production: " + "; ".join(problems))
    structlog.get_logger(__name__).warning("insecure_dev_configuration", problems=problems)
    return problems


__all__ = [
    "InsecureConfiguration",
    "advisories",
    "api_docs_enabled",
    "check_settings",
    "enforce",
    "is_production",
    "webhook_signatures_enforced",
]
