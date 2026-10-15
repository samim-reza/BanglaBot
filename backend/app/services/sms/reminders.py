"""Reminders: text live appointments / visits / viewings ``reminder_hours`` before they
start (once per record), from a lifespan loop."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import Merchant, Order, OrderStatus
from app.services.sms.composer import compose
from app.services.sms.policy import platform_ready, settings_of
from app.services.sms.sending import _item_name, send

logger = structlog.get_logger(__name__)

LIVE = (OrderStatus.pending, OrderStatus.confirmed)


async def send_due_reminders(now: datetime | None = None) -> int:
    """Text every live appointment / visit / viewing whose reminder time has come.

    A record is reminded once (``details.sms_reminder_at``), and only if it was
    booked before its reminder window opened — a same-day booking already got
    its confirmation text."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    async with AsyncSessionLocal() as session:
        merchants = list(await session.scalars(select(Merchant).where(Merchant.active.is_(True))))
    for merchant in merchants:
        config = settings_of(merchant)
        hours = int(config.get("reminder_hours") or 0)
        if not config["enabled"] or hours <= 0:
            continue
        horizon = now + timedelta(hours=hours)
        async with AsyncSessionLocal() as session:
            rows = list(
                await session.scalars(
                    select(Order).where(
                        Order.merchant_id == merchant.id,
                        Order.scheduled_at.is_not(None),
                        Order.scheduled_at > now,
                        Order.scheduled_at <= horizon,
                        Order.status.in_(LIVE),
                        Order.kind.in_(("appointment", "booking", "lead")),
                    )
                )
            )
            due: list[tuple[Order, str]] = []
            for row in rows:
                details = dict(row.details or {})
                if details.get("sms_reminder_at") or not row.customer_phone:
                    continue
                created = row.created_at or now
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if row.scheduled_at - created < timedelta(hours=hours):
                    continue
                details["sms_reminder_at"] = now.isoformat()
                row.details = details
                due.append((row, await _item_name(session, row.catalog_item_id)))
            await session.commit()
        for row, item_name in due:
            body = compose("reminder", row, merchant, item_name=item_name)
            if body:
                await send(merchant, row.customer_phone, body, kind="reminder", order_id=row.id)
                sent += 1
    return sent


async def run_reminders() -> None:
    """Lifespan task: send due reminders every few minutes."""
    interval = max(60, int(get_settings().sms_reminder_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        if not platform_ready():
            continue
        try:
            count = await send_due_reminders()
            if count:
                await logger.ainfo("sms_reminders_sent", count=count)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("sms_reminders_failed", error=str(exc))
