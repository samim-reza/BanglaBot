"""What happens after a booking changes: the customer's SMS and the calendar mirror.

Called fire-and-forget after an agent outcome (from the call store) and after a
manual change in the portal; nothing here can fail a call or a request.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def _after_outcome(merchant_id: str, record_id: str, outcome: str) -> None:
    from app.services import calendar_service, sms_service

    await asyncio.gather(
        sms_service.after_outcome(merchant_id, record_id, outcome),
        calendar_service.sync_record(record_id),
        return_exceptions=True,
    )


def after_outcome(merchant_id: str, record_id: str, outcome: str) -> None:
    """An agent wrote an outcome on a record: text the customer, mirror the calendar."""
    if record_id:
        asyncio.create_task(_after_outcome(merchant_id, record_id, outcome))


def after_record_change(record_id: str) -> None:
    """A record was created / edited in the portal: keep the calendar in step."""
    from app.services import calendar_service

    if record_id:
        asyncio.create_task(calendar_service.sync_record(record_id))


def after_record_delete(merchant: Any, details: dict[str, Any]) -> None:
    from app.services import calendar_service

    if details.get("google_event_id"):
        asyncio.create_task(calendar_service.delete_event(merchant, dict(details)))


__all__ = ["after_outcome", "after_record_change", "after_record_delete"]
