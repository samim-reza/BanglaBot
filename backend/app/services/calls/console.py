"""Test calls from the portal's console: browser voice (``web``) or text (``chat``)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.context import DIRECTION_OUTBOUND, CallContext
from app.models import CallLog, Merchant, Order
from app.verticals import flow_for
from app.voice.languages import normalize_language


async def open_test_call(
    db: AsyncSession,
    merchant: Merchant,
    *,
    direction: str,
    record: Order | None = None,
    caller_number: str = "",
    mode: str = "web",
) -> tuple[CallLog, CallContext]:
    """A call from the portal's test console: browser voice (``web``) or text (``chat``)."""
    if direction == DIRECTION_OUTBOUND and record is None:
        raise HTTPException(status_code=422, detail="Pick a record for an outbound test call")
    flow = flow_for(merchant, direction)
    log = CallLog(
        order_id=record.id if record is not None else None,
        merchant_id=merchant.id,
        call_status="in-progress",
        language=normalize_language(merchant.language),
        direction=mode,
        flow=flow.key,
        caller_number=caller_number,
    )
    db.add(log)
    await db.flush()
    from app.services.context_service import build_context

    ctx = await build_context(db, merchant, record=record, direction=direction, caller_number=caller_number, test=True)
    await db.commit()
    await db.refresh(log)
    return log, ctx
