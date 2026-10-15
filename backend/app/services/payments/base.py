"""The payments port: what every payment provider implements, and what it returns.

A provider turns ``(reference, amount, currency, description)`` into a link the
customer opens (``create_link``) and turns its own webhook calls into a
:class:`PaymentEvent` (``handle_webhook``). ``reference`` is always our
``payments.id``; the event carries it back so the service can find the row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

STATUS_PENDING = "pending"
STATUS_PAID = "paid"
STATUS_FAILED = "failed"
STATUS_REFUNDED = "refunded"
STATUS_EXPIRED = "expired"
PAYMENT_STATUSES = (STATUS_PENDING, STATUS_PAID, STATUS_FAILED, STATUS_REFUNDED, STATUS_EXPIRED)

KIND_ORDER = "order"
KIND_SUBSCRIPTION = "subscription"
KIND_ADDON = "addon"
KIND_OTHER = "other"
PAYMENT_KINDS = (KIND_ORDER, KIND_SUBSCRIPTION, KIND_ADDON, KIND_OTHER)


class PaymentError(Exception):
    """A payment could not be created / processed; ``str(exc)`` is safe to show (no secrets)."""


class WebhookSignatureError(PaymentError):
    """The webhook's signature is missing, wrong or too old."""


@dataclass(frozen=True)
class PaymentLink:
    url: str
    provider: str
    provider_ref: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PaymentEvent:
    """Something a provider told us about a payment."""

    provider: str
    #: paid | failed | refunded | expired
    status: str
    #: Our ``payments.id`` (dummy token ``r``, Stripe ``client_reference_id``).
    reference: str = ""
    provider_ref: str = ""
    amount: Decimal | None = None
    currency: str = ""
    event_id: str = ""
    event_type: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PaymentProvider(Protocol):
    name: str

    async def create_link(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: dict[str, Any],
        success_url: str | None = None,
    ) -> PaymentLink: ...

    async def handle_webhook(self, request_body: bytes, headers: Mapping[str, str]) -> PaymentEvent | None: ...


def money(value: Any) -> Decimal:
    """``value`` as a 2-decimal amount; raises ``PaymentError`` for junk or negatives."""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PaymentError("invalid amount") from exc
    if not amount.is_finite() or amount < 0:
        raise PaymentError("invalid amount")
    return amount


def currency_code(value: Any, default: str = "USD") -> str:
    code = "".join(ch for ch in str(value or "").upper() if ch.isalpha())[:3]
    return code if len(code) == 3 else default


def header(headers: Mapping[str, str] | Any, name: str) -> str:
    """A header from a Starlette ``Headers`` (case-insensitive) or a plain dict."""
    value = headers.get(name) if hasattr(headers, "get") else None
    if value is None and isinstance(headers, Mapping):
        lowered = name.lower()
        value = next((v for k, v in headers.items() if str(k).lower() == lowered), None)
    return str(value or "")


__all__ = [
    "KIND_ADDON",
    "KIND_ORDER",
    "KIND_OTHER",
    "KIND_SUBSCRIPTION",
    "PAYMENT_KINDS",
    "PAYMENT_STATUSES",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "STATUS_PAID",
    "STATUS_PENDING",
    "STATUS_REFUNDED",
    "PaymentError",
    "PaymentEvent",
    "PaymentLink",
    "PaymentProvider",
    "WebhookSignatureError",
    "currency_code",
    "header",
    "money",
]
