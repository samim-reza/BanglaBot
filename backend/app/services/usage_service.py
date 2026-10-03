"""This month's usage of an account against its plan."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addons import entitlements
from app.models import CallLog, Merchant, Message

#: Directions that are billable phone minutes / billable chats.
VOICE_DIRECTIONS = ("outbound", "inbound")
CHAT_DIRECTIONS = ("widget", "whatsapp", "messenger")


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def month_usage(db: AsyncSession, merchant: Merchant) -> dict[str, Any]:
    start = month_start()
    seconds = int(
        await db.scalar(
            select(func.coalesce(func.sum(CallLog.duration_secs), 0)).where(
                CallLog.merchant_id == merchant.id, CallLog.created_at >= start, CallLog.direction.in_(VOICE_DIRECTIONS)
            )
        )
        or 0
    )
    calls = int(
        await db.scalar(
            select(func.count(CallLog.id)).where(
                CallLog.merchant_id == merchant.id, CallLog.created_at >= start, CallLog.direction.in_(VOICE_DIRECTIONS)
            )
        )
        or 0
    )
    chats = int(
        await db.scalar(
            select(func.count(CallLog.id)).where(
                CallLog.merchant_id == merchant.id,
                CallLog.created_at >= start,
                CallLog.direction.in_(CHAT_DIRECTIONS),
                # Only conversations where the visitor actually wrote something.
                CallLog.transcript.like("%Customer:%"),
            )
        )
        or 0
    )
    sms = int(
        await db.scalar(
            select(func.count(Message.id)).where(
                Message.merchant_id == merchant.id,
                Message.created_at >= start,
                Message.status.in_(("queued", "sent", "delivered")),
            )
        )
        or 0
    )
    ent = entitlements(merchant)
    minutes = round(seconds / 60.0, 1)
    included = ent.minutes
    return {
        "plan": ent.plan.as_json(),
        # Plan + add-ons; null = no limit.
        "limits": ent.as_json()["limits"],
        "period_start": start.isoformat(),
        "minutes": minutes,
        "calls": calls,
        "chats": chats,
        "sms": sms,
        "minutes_left": max(0.0, included - minutes) if included else None,
        "overage_minutes": max(0.0, minutes - included) if included else 0.0,
    }


__all__ = ["month_usage"]
