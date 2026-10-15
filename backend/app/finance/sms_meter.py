"""SMS segments into the ledger: a periodic pass over ``messages``.

Texts are sent from several places (confirmations, reminders, the owner's
manual texts), so instead of hooking each one the finance jobs read messages
that settled (older than ``SETTLE_MINUTES``) since a watermark kept in
``platform_settings["finance.sms_watermark"]``. The watermark row is locked
for the pass, so concurrent workers never meter a message twice. Only texts
Telnyx accepted are billable (sent / delivered / read / undelivered).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.finance import ledger, pricebook, rollup
from app.finance.meter import CallMeter
from app.models import Message
from app.models.platform_setting import PlatformSetting
from app.models.usage import UsageEvent

WATERMARK_KEY = "finance.sms_watermark"
BILLABLE = ("sent", "delivered", "read", "undelivered")
SETTLE_MINUTES = 10
BATCH = 500


def _parse_watermark(value: Any, default_at: datetime) -> tuple[datetime, str]:
    try:
        return datetime.fromisoformat(str(value["at"])), str(value.get("id") or "")
    except (TypeError, KeyError, ValueError):
        return default_at, ""


def message_lines(messages: list[Any], book: pricebook.PriceBook) -> list[tuple[Any, list[ledger.LedgerLine]]]:
    """``[(message, lines)]`` for billable messages (pure)."""
    out = []
    for message in messages:
        if getattr(message, "status", "") not in BILLABLE:
            continue
        meter = CallMeter(book)
        meter.add_sms(int(getattr(message, "segments", 1) or 1), meta={"message_id": str(message.id), "kind": str(getattr(message, "kind", "") or "")})
        if meter.lines:
            out.append((message, meter.lines))
    return out


async def meter_sent_sms(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Meter settled texts since the watermark; commits. Returns messages metered."""
    stamp = now or utcnow()
    row = await db.get(PlatformSetting, WATERMARK_KEY, with_for_update=True)
    if row is None:
        start = stamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        row = PlatformSetting(key=WATERMARK_KEY, value={"at": start.isoformat(), "id": ""}, updated_by="system", updated_at=stamp)
        db.add(row)
        await db.flush()
    since_at, since_id = _parse_watermark(row.value, stamp)
    messages = list(
        await db.scalars(
            select(Message)
            .where(tuple_(Message.created_at, Message.id) > tuple_(since_at, since_id), Message.created_at <= stamp - timedelta(minutes=SETTLE_MINUTES))
            .order_by(Message.created_at, Message.id)
            .limit(BATCH)
        )
    )
    if not messages:
        await db.commit()
        return 0
    book = await pricebook.current(db, stamp.date())
    priced = message_lines(messages, book)
    rows: list[dict[str, Any]] = []
    groups: dict[tuple[str, Any], tuple[datetime, list[ledger.LedgerLine]]] = {}
    for message, lines in priced:
        rows += ledger.event_rows(lines, merchant_id=str(message.merchant_id), call_log_id=None, occurred_at=message.created_at)
        key = (str(message.merchant_id), rollup.day_of(message.created_at))
        groups.setdefault(key, (message.created_at, []))[1].extend(lines)
    if rows:
        await db.execute(insert(UsageEvent), rows)
    for (merchant_id, _day), (at, lines) in groups.items():
        await rollup.upsert(db, rollup.aggregate(lines, merchant_id=merchant_id, occurred_at=at))
    last = messages[-1]
    row.value = {"at": last.created_at.isoformat(), "id": str(last.id)}
    row.updated_at = stamp
    await db.commit()
    from app.finance import guard

    guard.record_spend([line for _, lines in priced for line in lines])
    return len(priced)


__all__ = ["BILLABLE", "WATERMARK_KEY", "message_lines", "meter_sent_sms"]
