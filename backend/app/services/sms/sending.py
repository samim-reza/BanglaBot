"""Sending: one logged SMS through Telnyx, delivery receipts, and the text an agent
outcome triggers (deduplicated per record and kind)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.core.ratelimit import backends
from app.core.regions import normalize_phone, region_of
from app.db.session import AsyncSessionLocal
from app.models import CatalogItem, Merchant, Message, Order
from app.services import telnyx
from app.services.sms.composer import compose, segments
from app.services.sms.policy import planned_kind, platform_ready

logger = structlog.get_logger(__name__)

DAY_SECONDS = 86_400
CAPPED = "Daily text limit reached for this account or number."


async def _over_daily_cap(merchant_id: str, to_number: str) -> bool:
    """Counts this text against the account's and the number's daily caps; True when over.
    Chat visitors type the number a confirmation goes to, so both are bounded."""
    settings = get_settings()
    per_account = max(1, int(getattr(settings, "sms_daily_cap_per_account", 300) or 300))
    per_number = max(1, int(getattr(settings, "sms_daily_cap_per_number", 10) or 10))
    if await backends.call("hit", f"sms-number:{to_number}", per_number, float(DAY_SECONDS)):
        return True  # a refused number doesn't use up the account's budget
    return bool(await backends.call("hit", f"sms-account:{merchant_id}", per_account, float(DAY_SECONDS)))


def _sms_status_url(message_id: str) -> str | None:
    """The signed per-message receipt URL (Telnyx only calls public https endpoints)."""
    from app.services import telnyx_urls

    base = str(get_settings().public_base_url or "").rstrip("/")
    return telnyx_urls.sms_status_url(message_id, base) if base.startswith("https://") else None


async def send(merchant: Merchant, to: str, body: str, *, kind: str, order_id: str | None = None) -> Message:
    """Send one SMS (logged whatever happens). Never raises for delivery problems."""
    to_number = normalize_phone(to, region_of(merchant))
    async with AsyncSessionLocal() as session:
        message = Message(
            merchant_id=merchant.id, order_id=order_id, kind=kind, to_number=to_number, body=body,
            status="queued", segments=segments(body),
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
    if not platform_ready():
        await _update(message.id, status="skipped", error="SMS is not configured on the platform (Telnyx API key / sender).")
        message.status = "skipped"
        return message
    if await _over_daily_cap(str(merchant.id), to_number):
        await _update(message.id, status="skipped", error=CAPPED)
        message.status, message.error = "skipped", CAPPED
        await logger.awarning("sms_daily_cap", merchant_id=merchant.id, kind=kind, to=to_number)
        return message
    callback = _sms_status_url(message.id)
    try:
        sid = await telnyx.send_sms(to=to_number, text=body, webhook_url=callback, from_number=telnyx.number_for(merchant))
        await _update(message.id, status="sent", provider_sid=sid)
        message.status, message.provider_sid = "sent", sid
        await logger.ainfo("sms_sent", merchant_id=merchant.id, kind=kind, to=to_number, sid=sid)
    except Exception as exc:  # noqa: BLE001 — a failed text never breaks the call / request
        detail = getattr(exc, "detail", None) or str(exc)
        await _update(message.id, status="failed", error=str(detail)[:500])
        message.status, message.error = "failed", str(detail)[:500]
        await logger.awarning("sms_failed", merchant_id=merchant.id, kind=kind, to=to_number, error=str(detail)[:200])
    return message


async def _update(message_id: str, **fields: Any) -> None:
    async with AsyncSessionLocal() as session:
        message = await session.get(Message, message_id)
        if message is None:
            return
        for key, value in fields.items():
            setattr(message, key, value)
        message.updated_at = utcnow()
        await session.commit()


#: Telnyx recipient status → ours.
TELNYX_STATUS = {
    "queued": "queued",
    "sending": "sent",
    "sent": "sent",
    "delivery_unconfirmed": "sent",
    "delivered": "delivered",
    "read": "read",
    "expired": "undelivered",
    "delivery_failed": "undelivered",
    "sending_failed": "failed",
}


async def apply_status(message_id: str, status: str, error: str = "", *, provider_sid: str = "") -> None:
    """Telnyx delivery receipt, matched by our message id or else by Telnyx's."""
    mapped = TELNYX_STATUS.get(str(status or "").lower())
    if mapped is None:
        return
    if not message_id and provider_sid:
        async with AsyncSessionLocal() as session:
            message_id = str(await session.scalar(select(Message.id).where(Message.provider_sid == provider_sid)) or "")
    if not message_id:
        return
    fields: dict[str, Any] = {"status": mapped}
    if error:
        fields["error"] = str(error)[:500]
    await _update(message_id, **fields)


async def _item_name(session: Any, item_id: str | None) -> str:
    if not item_id:
        return ""
    item = await session.get(CatalogItem, item_id)
    return item.name if item is not None else ""


async def after_outcome(merchant_id: str, record_id: str, outcome: str) -> None:
    """The text a call / chat outcome triggers (confirmation, change, cancellation…)."""
    try:
        async with AsyncSessionLocal() as session:
            merchant = await session.get(Merchant, merchant_id)
            record = await session.get(Order, record_id) if record_id else None
            if merchant is None or record is None:
                return
            kind = planned_kind(merchant, outcome, record_kind=record.kind or "", phone=record.customer_phone or "")
            if kind is None:
                return
            # The same outcome can be written twice (an order confirmed, then its address
            # checked): one text per record and kind within a few minutes.
            recent = await session.scalar(
                select(Message.id).where(
                    Message.order_id == record.id,
                    Message.kind == kind,
                    Message.created_at >= utcnow() - timedelta(minutes=15),
                ).limit(1)
            )
            if recent:
                return
            body = compose(kind, record, merchant, item_name=await _item_name(session, record.catalog_item_id))
        if body:
            await send(merchant, record.customer_phone, body, kind=kind, order_id=record.id)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("sms_after_outcome_failed", record_id=record_id, error=str(exc))
