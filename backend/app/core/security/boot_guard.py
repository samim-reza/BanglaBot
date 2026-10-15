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
    return problems


def enforce(settings: Any) -> list[str]:
    """Raise ``InsecureConfiguration`` in production; log a warning otherwise."""
    problems = check_settings(settings)
    if not problems:
        return problems
    if is_production(settings):
        raise InsecureConfiguration("Refusing to start in production: " + "; ".join(problems))
    structlog.get_logger(__name__).warning("insecure_dev_configuration", problems=problems)
    return problems


__all__ = ["InsecureConfiguration", "check_settings", "enforce", "is_production"]
