"""Stripe Checkout over the REST API (httpx, no SDK).

``create_link`` opens a one-off Checkout Session (``mode=payment``) whose
``client_reference_id`` is our ``payments.id``; ``handle_webhook`` verifies the
``Stripe-Signature`` header (HMAC-SHA256 of ``"{t}.{body}"``, replay window
``tolerance``) and maps Checkout / refund events onto :class:`PaymentEvent`.
Enabled when ``STRIPE_SECRET_KEY`` and ``STRIPE_WEBHOOK_SECRET`` are both set.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from app.services.payments.base import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PAID,
    STATUS_REFUNDED,
    PaymentError,
    PaymentEvent,
    PaymentLink,
    WebhookSignatureError,
    currency_code,
    header,
    money,
)

PROVIDER = "stripe"
DEFAULT_TOLERANCE_SECONDS = 300
#: Currencies Stripe takes in whole units (no cents).
ZERO_DECIMAL = frozenset({"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"})
MAX_METADATA_KEYS = 20


def minor_units(amount: Decimal, currency: str) -> int:
    value = money(amount)
    return int(value if currency_code(currency) in ZERO_DECIMAL else (value * 100).to_integral_value())


def from_minor(units: Any, currency: str) -> Decimal | None:
    try:
        value = Decimal(int(units))
    except (TypeError, ValueError):
        return None
    return money(value if currency_code(currency) in ZERO_DECIMAL else value / 100)


def verify_signature(payload: bytes, signature_header: str, secret: str, *, tolerance: int = DEFAULT_TOLERANCE_SECONDS, now: float | None = None) -> int:
    """The signed timestamp of a valid ``Stripe-Signature``; ``WebhookSignatureError`` otherwise."""
    if not secret:
        raise WebhookSignatureError("webhook secret not configured")
    stamp, signatures = "", []
    for part in str(signature_header or "").split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            stamp = value
        elif key == "v1" and value:
            signatures.append(value)
    if not stamp or not signatures:
        raise WebhookSignatureError("missing signature")
    try:
        signed_at = int(stamp)
    except ValueError as exc:
        raise WebhookSignatureError("bad signature timestamp") from exc
    expected = hmac.new(secret.encode("utf-8"), stamp.encode("ascii") + b"." + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures if candidate.isascii()):
        raise WebhookSignatureError("signature mismatch")
    current = time.time() if now is None else now
    if tolerance and abs(current - signed_at) > tolerance:
        raise WebhookSignatureError("signature too old")
    return signed_at


def _session_event(event_type: str, obj: dict[str, Any]) -> str | None:
    if event_type == "checkout.session.completed":
        # Delayed methods (bank debits) complete unpaid and report later.
        return STATUS_PAID if obj.get("payment_status") in ("paid", "no_payment_required") else None
    return {
        "checkout.session.async_payment_succeeded": STATUS_PAID,
        "checkout.session.async_payment_failed": STATUS_FAILED,
        "checkout.session.expired": STATUS_EXPIRED,
    }.get(event_type)


def parse_event(event: dict[str, Any]) -> PaymentEvent | None:
    """A verified Stripe event → our event (None for types we don't act on)."""
    event_type = str(event.get("type") or "")
    obj = ((event.get("data") or {}).get("object")) or {}
    if not isinstance(obj, dict):
        return None
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    currency = currency_code(obj.get("currency"))
    if event_type.startswith("checkout.session."):
        status = _session_event(event_type, obj)
        if status is None:
            return None
        return PaymentEvent(
            provider=PROVIDER,
            status=status,
            reference=str(obj.get("client_reference_id") or metadata.get("reference") or ""),
            provider_ref=str(obj.get("id") or ""),
            amount=from_minor(obj.get("amount_total"), currency),
            currency=currency,
            event_id=str(event.get("id") or ""),
            event_type=event_type,
            meta={"payment_intent": str(obj.get("payment_intent") or "")},
        )
    if event_type == "charge.refunded" and obj.get("refunded"):
        return PaymentEvent(
            provider=PROVIDER,
            status=STATUS_REFUNDED,
            reference=str(metadata.get("reference") or ""),
            amount=from_minor(obj.get("amount_refunded"), currency),
            currency=currency,
            event_id=str(event.get("id") or ""),
            event_type=event_type,
            meta={"payment_intent": str(obj.get("payment_intent") or "")},
        )
    return None


class StripeProvider:
    name = PROVIDER

    def __init__(
        self,
        *,
        secret_key: str,
        webhook_secret: str,
        api_base: str = "https://api.stripe.com",
        tolerance: int = DEFAULT_TOLERANCE_SECONDS,
        ttl_seconds: int = 24 * 3600,
        return_base: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not secret_key or not webhook_secret:
            raise PaymentError("Stripe is not configured")
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self.api_base = api_base.rstrip("/")
        self.tolerance = int(tolerance)
        self.ttl_seconds = max(1800, min(24 * 3600, int(ttl_seconds)))
        self._return_base = return_base
        self._transport = transport

    def _base(self) -> str:
        if self._return_base is not None:
            return self._return_base.rstrip("/")
        from app.services.payments.config import frontend_base

        return frontend_base()

    def session_form(self, *, reference: str, amount: Decimal, currency: str, description: str, metadata: dict[str, Any], success_url: str | None) -> list[tuple[str, str]]:
        code = currency_code(currency)
        base = self._base()
        form = [
            ("mode", "payment"),
            ("client_reference_id", reference),
            ("success_url", success_url or f"{base}/pay/success?ref={reference}"),
            ("cancel_url", f"{base}/pay/cancelled?ref={reference}"),
            ("expires_at", str(int(time.time()) + self.ttl_seconds)),
            ("line_items[0][quantity]", "1"),
            ("line_items[0][price_data][currency]", code.lower()),
            ("line_items[0][price_data][unit_amount]", str(minor_units(amount, code))),
            ("line_items[0][price_data][product_data][name]", (description or "Payment")[:200]),
            ("metadata[reference]", reference),
            ("payment_intent_data[metadata][reference]", reference),
        ]
        extra = [(str(k)[:40], str(v)[:500]) for k, v in (metadata or {}).items() if k != "reference" and v not in (None, "")]
        form += [(f"metadata[{key}]", value) for key, value in extra[:MAX_METADATA_KEYS]]
        return form

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
        form = self.session_form(reference=reference, amount=amount, currency=currency, description=description, metadata=metadata, success_url=success_url)
        headers = {
            "Authorization": f"Bearer {self._secret_key}",
            "Idempotency-Key": f"checkout-{reference}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15.0, transport=self._transport) as client:
                response = await client.post("/v1/checkout/sessions", content=urlencode(form).encode("ascii"), headers=headers)
        except httpx.HTTPError as exc:
            raise PaymentError(f"Stripe is unreachable ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            try:
                message = str(((response.json() or {}).get("error") or {}).get("message") or "")[:200]
            except ValueError:
                message = ""
            raise PaymentError(f"Stripe refused the checkout session (HTTP {response.status_code}) {message}".strip())
        data = response.json()
        expires = data.get("expires_at")
        return PaymentLink(
            url=str(data.get("url") or ""),
            provider=PROVIDER,
            provider_ref=str(data.get("id") or ""),
            expires_at=datetime.fromtimestamp(int(expires), tz=timezone.utc) if expires else None,
        )

    async def handle_webhook(self, request_body: bytes, headers: Mapping[str, str]) -> PaymentEvent | None:
        verify_signature(request_body, header(headers, "stripe-signature"), self._webhook_secret, tolerance=self.tolerance)
        try:
            event = json.loads(request_body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise PaymentError("webhook body is not JSON") from exc
        return parse_event(event) if isinstance(event, dict) else None


__all__ = ["PROVIDER", "StripeProvider", "from_minor", "minor_units", "parse_event", "verify_signature"]
