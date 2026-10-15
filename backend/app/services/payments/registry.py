"""Which provider makes a link: the owner's own link, or the platform's (dummy / Stripe)."""

from __future__ import annotations

from typing import Any

import structlog

from app.services.payments import link as owner_link
from app.services.payments.base import PaymentProvider
from app.services.payments.config import PaymentSettings, get_payment_settings
from app.services.payments.dummy import DummyProvider
from app.services.payments.stripe import StripeProvider

logger = structlog.get_logger(__name__)

PLATFORM_PROVIDERS = ("dummy", "stripe")
_warned = False


def stripe_provider(settings: PaymentSettings | None = None) -> StripeProvider | None:
    s = settings or get_payment_settings()
    if not s.stripe_ready():
        return None
    return StripeProvider(
        secret_key=s.stripe_secret_key or "",
        webhook_secret=s.stripe_webhook_secret or "",
        api_base=s.stripe_api_base,
        tolerance=s.stripe_webhook_tolerance_seconds,
        ttl_seconds=s.link_ttl_seconds(),
    )


def platform_provider(settings: PaymentSettings | None = None) -> PaymentProvider:
    """``PAYMENT_PROVIDER``: Stripe when chosen and configured, else the dummy pay page."""
    global _warned
    s = settings or get_payment_settings()
    if s.payment_provider == "stripe":
        provider = stripe_provider(s)
        if provider is not None:
            return provider
        if not _warned:
            _warned = True
            logger.warning("stripe_not_configured", hint="set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET; using the dummy pay page")
    return DummyProvider(ttl_seconds=s.link_ttl_seconds())


def get_provider(merchant: Any | None = None) -> PaymentProvider:
    """The provider for a booking of ``merchant`` (its own link when it chose one);
    without a merchant (subscriptions, add-ons) always the platform's."""
    if merchant is not None:
        config = owner_link.settings_of(merchant)
        if config["provider"] == owner_link.PROVIDER and config["link_template"]:
            return owner_link.OwnerLinkProvider(config["link_template"])
    return platform_provider()


def webhook_provider(name: str) -> PaymentProvider | None:
    """The provider whose webhook endpoint was called (only Stripe sends webhooks)."""
    if name == "stripe":
        return stripe_provider()
    return None


__all__ = ["PLATFORM_PROVIDERS", "get_provider", "platform_provider", "stripe_provider", "webhook_provider"]
