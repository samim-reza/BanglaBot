"""Inbound texts (Telnyx ``message.received`` on the messaging profile's webhook): the
STOP / START / HELP keywords. Anything else a customer texts is ignored here.

STOP and friends opt the number out of texts from the number they wrote to (and from
the account that number belongs to); START / UNSTOP / YES opt back in; HELP / INFO gets
one short reply (at most once an hour per number). Never raises.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import select

from app.core.ratelimit import backends
from app.db.session import AsyncSessionLocal
from app.models import Merchant, Message
from app.services.sms import optout

logger = structlog.get_logger(__name__)

HELP_REPLY_WINDOW_SECONDS = 3600
#: Detached HELP replies (strong references).
_pending: set[asyncio.Task[Any]] = set()


def parse(payload: Any) -> tuple[str, str, str]:
    """``(text, customer number, our number)`` of a ``message.received`` payload."""
    if not isinstance(payload, dict):
        return "", "", ""
    sender = payload.get("from")
    phone = sender.get("phone_number") if isinstance(sender, dict) else sender
    recipients = payload.get("to") or []
    first = recipients[0] if isinstance(recipients, list) and recipients else recipients
    ours = first.get("phone_number") if isinstance(first, dict) else first
    return str(payload.get("text") or ""), optout.canonical(phone), optout.canonical(ours)


async def _merchant_for(session: Any, ours: str, phone: str) -> Merchant | None:
    """The account the reply is meant for: the owner of the number, else the last account
    that texted this customer (accounts without their own number share the platform's)."""
    from app.services.calls.inbound import find_inbound_merchant

    merchant = await find_inbound_merchant(session, ours) if ours else None
    if merchant is not None:
        return merchant
    merchant_id = await session.scalar(
        select(Message.merchant_id).where(Message.to_number == phone).order_by(Message.created_at.desc()).limit(1)
    )
    return await session.get(Merchant, merchant_id) if merchant_id else None


async def handle(payload: Any) -> str:
    """Act on one inbound text; returns the action taken (``stop`` / ``start`` / ``help`` / "")."""
    text, phone, ours = parse(payload)
    action = optout.action_of(text)
    if not action or not phone:
        return ""
    try:
        async with AsyncSessionLocal() as session:
            merchant = await _merchant_for(session, ours, phone)
            if action == "stop":
                await optout.record(session, sender=ours, phone=phone, merchant_id=getattr(merchant, "id", None), keyword=optout.keyword_of(text))
                await session.commit()
            elif action == "start":
                await optout.remove(session, sender=ours, phone=phone, merchant_id=getattr(merchant, "id", None))
                await session.commit()
        if action == "help":
            task = asyncio.get_running_loop().create_task(reply_help(merchant, phone, ours))
            _pending.add(task)
            task.add_done_callback(_pending.discard)
        await logger.ainfo("sms_keyword", action=action, to=ours, merchant_id=getattr(merchant, "id", ""))
        return action
    except Exception as exc:  # noqa: BLE001 — the webhook always answers 204
        await logger.awarning("sms_keyword_failed", action=action, error=str(exc)[:200])
        return ""


async def reply_help(merchant: Merchant | None, phone: str, ours: str) -> str:
    """The HELP text, once an hour per (number, customer). Returns the status ("" = not sent)."""
    try:
        if await backends.call("hit", f"sms-help:{ours}:{phone}", 1, float(HELP_REPLY_WINDOW_SECONDS)):
            return ""
        if merchant is not None:
            from app.services.sms.sending import send

            body = optout.help_text(merchant.business_name, str(merchant.support_phone or merchant.phone or ""))
            return (await send(merchant, phone, body, kind="help")).status
        # Nobody to attribute it to (a shared number nobody texted them from): the platform answers.
        from app.services import telnyx
        from app.services.sms.policy import platform_ready

        if not platform_ready():
            return ""
        await telnyx.send_sms(to=phone, text=optout.help_text("Callisa"), from_number=ours or None)
        return "sent"
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("sms_help_reply_failed", error=str(exc)[:200])
        return ""


__all__ = ["handle", "parse", "reply_help"]
