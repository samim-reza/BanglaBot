"""Webhook add-on: a signed JSON event to the business's own system when a call or chat ends.

Body: ``{"event": "call.completed", "account": {...}, "call": {...}, "record": {...} | null}``.
Header ``X-Agent-Signature: sha256=<hex>`` is HMAC-SHA256 of the raw body with the
account's webhook secret, so the receiver can verify it came from us. The owner types
the URL, so it goes through the SSRF guard (public addresses only, pinned DNS, no
redirects).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import structlog

from app.core.datetime_utils import utcnow
from app.core.security import outbound
from app.db.session import AsyncSessionLocal
from app.models import CallLog, Merchant, Order

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 6.0
#: The receiver's answer is only read for its status.
MAX_RESPONSE_BYTES = 64_000


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def post_event(merchant: Merchant, payload: dict[str, Any]) -> dict[str, Any]:
    from app.core.addons import entitlements

    if not entitlements(merchant).api_webhooks:
        # A URL saved before a downgrade: the plan no longer includes webhooks.
        return {"ok": False, "error": "Webhooks aren't included in this plan"}
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "voice-agent-webhooks/1"}
    # Stored encrypted; the property decrypts (legacy plaintext rows read as-is).
    secret = merchant.webhook_secret
    if secret:
        headers["X-Agent-Signature"] = sign(secret, body)
    elif getattr(merchant, "webhook_secret_stored", ""):
        await logger.awarning("webhook_secret_unreadable", merchant_id=merchant.id, hint="ENCRYPTION_SECRET changed; rotate the secret")
    try:
        response = await outbound.request(
            "POST", merchant.webhook_url, content=body, headers=headers, timeout=TIMEOUT_SECONDS, max_bytes=MAX_RESPONSE_BYTES
        )
        ok = 200 <= response.status_code < 300
        # Not ``event=``: that is structlog's message argument (a TypeError that made every delivery look failed).
        await logger.ainfo("webhook_sent", merchant_id=merchant.id, status=response.status_code, webhook_event=payload.get("event"))
        return {"ok": ok, "status": response.status_code}
    except Exception as exc:  # noqa: BLE001 — the business's endpoint being down never affects calls
        await logger.awarning("webhook_failed", merchant_id=merchant.id, error=outbound.describe_error(exc), error_type=type(exc).__name__)
        # A generic reason only: the owner must not learn what an internal address answered.
        return {"ok": False, "error": outbound.describe_error(exc)}


def _record(order: Order | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "id": order.id,
        "kind": order.kind,
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "address": order.address,
        "summary": order.items_summary,
        "amount": str(order.total_amount),
        "currency": order.currency,
        "scheduled_at": order.scheduled_at.isoformat() if order.scheduled_at else None,
        "catalog_item_id": order.catalog_item_id,
        "details": dict(order.details or {}),
        "collected": dict(order.flow_data or {}),
    }


async def send_call_finished(call_log_id: str) -> None:
    async with AsyncSessionLocal() as session:
        log = await session.get(CallLog, call_log_id)
        if log is None:
            return
        merchant = await session.get(Merchant, log.merchant_id)
        if merchant is None or not merchant.webhook_url:
            return
        order = await session.get(Order, log.order_id) if log.order_id else None
    payload = {
        "event": "call.completed",
        "sent_at": utcnow().isoformat(),
        "account": {"id": merchant.id, "business_name": merchant.business_name, "vertical": merchant.vertical},
        "call": {
            "id": log.id,
            "direction": log.direction,
            "flow": log.flow,
            "caller_number": log.caller_number,
            "outcome": log.outcome,
            "duration_secs": log.duration_secs,
            "language": log.language,
            "transcript": log.transcript,
        },
        "record": _record(order),
    }
    await post_event(merchant, payload)


async def send_test_event(merchant: Merchant) -> dict[str, Any]:
    payload = {
        "event": "test",
        "sent_at": utcnow().isoformat(),
        "account": {"id": merchant.id, "business_name": merchant.business_name, "vertical": merchant.vertical},
        "message": "Webhook test from your voice agent.",
    }
    return await post_event(merchant, payload)


__all__ = ["post_event", "send_call_finished", "send_test_event", "sign"]
