"""Payment knobs, read from the same ``.env`` files as the app settings.

Kept apart from :mod:`app.core.config` so the payments layer owns its settings
(the same pattern as ``app.voice.providers.settings``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _settings_env_files, get_settings


class PaymentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_settings_env_files(), env_file_encoding="utf-8", extra="ignore")

    #: dummy (our own test pay page) | stripe (Checkout; needs both Stripe keys below).
    payment_provider: str = "dummy"
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_api_base: str = "https://api.stripe.com"
    #: Oldest Stripe-Signature timestamp accepted (replay window).
    stripe_webhook_tolerance_seconds: int = 300
    #: How long a payment link works (Stripe allows 30 min – 24 h).
    payment_link_ttl_hours: int = 24
    #: How often unpaid holds are released / stale links expired.
    payment_sweep_interval_seconds: int = 60

    @field_validator("stripe_secret_key", "stripe_webhook_secret", mode="before")
    @classmethod
    def _blank_as_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value or None

    @field_validator("payment_provider", mode="before")
    @classmethod
    def _provider(cls, value):
        return str(value or "dummy").strip().lower() or "dummy"

    def stripe_ready(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    def link_ttl_seconds(self) -> int:
        return max(1800, min(24 * 3600, int(self.payment_link_ttl_hours or 24) * 3600))


@lru_cache
def get_payment_settings() -> PaymentSettings:
    return PaymentSettings()


def frontend_base() -> str:
    """The portal origin pay pages live on (the first ``FRONTEND_ORIGIN`` entry)."""
    raw = str(get_settings().frontend_origin or "")
    first = next((part.strip() for part in raw.split(",") if part.strip()), "http://localhost:3000")
    return first.rstrip("/")


__all__ = ["PaymentSettings", "frontend_base", "get_payment_settings"]
