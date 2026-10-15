"""Payments: one port, three providers (dummy pay page, Stripe Checkout, the owner's own link).

The contract other workstreams build on (keep stable):

- ``PaymentProvider.create_link(*, reference, amount, currency, description, metadata,
  success_url=None) -> PaymentLink(url, provider, provider_ref, expires_at)``
- ``PaymentProvider.handle_webhook(request_body, headers) -> PaymentEvent | None``
- ``get_provider(merchant=None)`` — the owner's link for a booking, else the platform default
  (``PAYMENT_PROVIDER=dummy|stripe``).
- ``service.create_payment(db, merchant_id=, amount=, currency=, description=, kind="subscription",
  subscription_id=, success_url=)`` — a pending ``payments`` row with its link (caller commits).
- ``service.on_paid("subscription", handler)`` — ``await handler(db, payment)`` runs in the
  transaction that marks such a payment paid (webhook / pay page), so it can switch the plan on.

Modules: ``base`` (port + types), ``dummy``, ``stripe``, ``link`` (owner link + settings),
``registry``, ``records`` (booking changes), ``service``, ``pay_page``, ``holds`` (sweeper).
"""

from app.services.payments.base import (
    KIND_ADDON,
    KIND_ORDER,
    KIND_SUBSCRIPTION,
    PaymentError,
    PaymentEvent,
    PaymentLink,
    PaymentProvider,
    WebhookSignatureError,
)
from app.services.payments.registry import get_provider, platform_provider

__all__ = [
    "KIND_ADDON",
    "KIND_ORDER",
    "KIND_SUBSCRIPTION",
    "PaymentError",
    "PaymentEvent",
    "PaymentLink",
    "PaymentProvider",
    "WebhookSignatureError",
    "get_provider",
    "platform_provider",
]
