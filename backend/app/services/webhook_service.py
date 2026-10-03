"""Webhook add-on: a signed JSON event to the business's own system when a call or chat ends.

Body: ``{"event": "call.completed", "account": {...}, "call": {...}, "record": {...} | null}``.
Header ``X-Agent-Signature: sha256=<hex>`` is HMAC-SHA256 of the raw body with the
account's webhook secret, so the receiver can verify it came from us.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import structlog

from app.core.datetime_utils import utcnow
from app.db.session import AsyncSessionLocal
from app.models import CallLog, Merchant, Order
from app.voice.llm import shared_client

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 6.0


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def post_event(merchant: Merchant, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "voice-agent-webhooks/1"}
    if merchant.webhook_secret:
        headers["X-Agent-Signature"] = sign(merchant.webhook_secret, body)
    try:
        response = await shared_client().post(merchant.webhook_url, content=body, headers=headers, timeout=TIMEOUT_SECONDS)
        ok = 200 <= response.status_code < 300
        await logger.ainfo("webhook_sent", merchant_id=merchant.id, status=response.status_code, event=payload.get("event"))
        return {"ok": ok, "status": response.status_code}
    except Exception as exc:  # noqa: BLE001 — the business's endpoint being down never affects calls
        await logger.awarning("webhook_failed", merchant_id=merchant.id, error=str(exc))
        return {"ok": False, "error": str(exc)[:200]}


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
