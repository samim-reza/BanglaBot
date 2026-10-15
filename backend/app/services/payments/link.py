"""The owner's own payment link, and the account's payment settings.

An owner who already takes payments elsewhere (a Stripe Payment Link, PayPal.me,
bKash merchant page, ...) gives a URL template; ``{amount}``, ``{currency}`` and
``{ref}`` are filled in per booking. Nothing reports back from such a link: the
owner marks the booking paid in the portal.

``merchants.payment_settings``::

    {"provider": "platform" | "link", "link_template": "https://...", "methods": ["online", "at_venue"]}
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlsplit

from app.services.payments.base import PaymentError, PaymentEvent, PaymentLink, currency_code, money

PROVIDER = "link"
PROVIDER_PLATFORM = "platform"
PROVIDER_CHOICES = (PROVIDER_PLATFORM, PROVIDER)
METHODS = ("online", "at_venue")
DEFAULT_SETTINGS: dict[str, Any] = {"provider": PROVIDER_PLATFORM, "link_template": "", "methods": list(METHODS)}
MAX_TEMPLATE_CHARS = 500
PLACEHOLDERS = ("amount", "currency", "ref")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


def validate_template(template: str) -> str:
    """A clean template or ``ValueError`` (message safe to show)."""
    value = str(template or "").strip()
    if not value:
        return ""
    if len(value) > MAX_TEMPLATE_CHARS:
        raise ValueError(f"Use at most {MAX_TEMPLATE_CHARS} characters")
    unknown = sorted({name for name in _PLACEHOLDER.findall(value) if name not in PLACEHOLDERS})
    if unknown:
        raise ValueError("Unknown placeholder: " + ", ".join("{" + name + "}" for name in unknown) + " (use {amount}, {currency}, {ref})")
    parts = urlsplit(value.replace("{", "").replace("}", ""))
    if parts.scheme != "https" or not parts.netloc or any(ch.isspace() for ch in value):
        raise ValueError("The link must be a full https:// address")
    return value


def fill(template: str, *, amount: Decimal, currency: str, reference: str) -> str:
    values = {"amount": str(money(amount)), "currency": currency_code(currency), "ref": str(reference)}
    return _PLACEHOLDER.sub(lambda m: quote(values.get(m.group(1), ""), safe=""), template)


def settings_of(merchant: Any) -> dict[str, Any]:
    """The account's payment settings with defaults for whatever is missing."""
    stored = getattr(merchant, "payment_settings", None)
    merged = {**DEFAULT_SETTINGS, "methods": list(METHODS)}
    if not isinstance(stored, dict):
        return merged
    if stored.get("provider") in PROVIDER_CHOICES:
        merged["provider"] = stored["provider"]
    if isinstance(stored.get("link_template"), str):
        merged["link_template"] = stored["link_template"]
    methods = stored.get("methods")
    if isinstance(methods, list):
        merged["methods"] = [method for method in METHODS if method in methods]
    return merged


def updated_settings(merchant: Any, changes: Mapping[str, Any]) -> dict[str, Any]:
    """The settings after ``changes``; ``ValueError`` when they don't make sense."""
    current = settings_of(merchant)
    if changes.get("link_template") is not None:
        current["link_template"] = validate_template(changes["link_template"])
    if changes.get("provider") is not None:
        if changes["provider"] not in PROVIDER_CHOICES:
            raise ValueError("provider must be 'platform' or 'link'")
        current["provider"] = changes["provider"]
    if changes.get("methods") is not None:
        current["methods"] = [method for method in METHODS if method in list(changes["methods"])]
        if not current["methods"]:
            raise ValueError("Accept at least one payment method")
    if current["provider"] == PROVIDER and not current["link_template"]:
        raise ValueError("Add your payment link first")
    return current


class OwnerLinkProvider:
    name = PROVIDER

    def __init__(self, template: str) -> None:
        if not template:
            raise PaymentError("No payment link set")
        self.template = template

    async def create_link(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: dict[str, Any],
        success_url: str | None = None,
    ) -> PaymentLink:
        return PaymentLink(url=fill(self.template, amount=amount, currency=currency, reference=reference), provider=PROVIDER, provider_ref=reference, expires_at=None)

    async def handle_webhook(self, request_body: bytes, headers: Mapping[str, str]) -> PaymentEvent | None:
        return None


__all__ = [
    "DEFAULT_SETTINGS",
    "METHODS",
    "PROVIDER",
    "PROVIDER_CHOICES",
    "PROVIDER_PLATFORM",
    "OwnerLinkProvider",
    "fill",
    "settings_of",
    "updated_settings",
    "validate_template",
]
