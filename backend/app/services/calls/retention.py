"""Call recordings are kept for the account's retention — 30 days, or 12 months with Pro or the
"12-month recordings" add-on — as the privacy policy says.

Past that a recording is no longer served. With ``RECORDING_PURGE=true`` a daily sweep also
deletes it at Telnyx and clears it from the call log."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.core.entitlements import entitlements
from app.core.plans import FEATURE_RECORDING_RETENTION
from app.models import CallLog, Merchant
from app.services import telnyx

logger = structlog.get_logger(__name__)

DEFAULT_DAYS = 30
EXTENDED_DAYS = 365
SWEEP_SECONDS = 6 * 3600.0
BATCH = 200


def retention_days(merchant: Any) -> int:
    return EXTENDED_DAYS if entitlements(merchant).has_feature(FEATURE_RECORDING_RETENTION) else DEFAULT_DAYS


def expired(log: Any, merchant: Any, now: datetime | None = None) -> bool:
    created = getattr(log, "created_at", None)
    if created is None:
        return False
    return created + timedelta(days=retention_days(merchant)) < (now or utcnow())


def ensure_available(log: Any, merchant: Any, now: datetime | None = None) -> None:
    """410 for a recording past the account's retention."""
    if merchant is not None and expired(log, merchant, now):
        raise HTTPException(status_code=410, detail=f"Recording deleted after {retention_days(merchant)} days")


async def purge_once(session: AsyncSession, now: datetime | None = None, limit: int = BATCH) -> int:
    """Delete up to ``limit`` expired recordings at Telnyx; returns how many were removed."""
    now = now or utcnow()
    rows = (
        await session.execute(
            select(CallLog, Merchant)
            .join(Merchant, Merchant.id == CallLog.merchant_id)
            .where(CallLog.recording_sid != "", CallLog.created_at < now - timedelta(days=DEFAULT_DAYS))
            .order_by(CallLog.created_at)
            .limit(limit)
        )
    ).all()
    removed = 0
    for log, merchant in rows:
        if not expired(log, merchant, now):
            continue  # 12-month retention: not yet
        try:
            await telnyx.delete_recording(log.recording_sid)
        except telnyx.TelnyxError as exc:
            await logger.awarning("recording_purge_failed", call_log_id=log.id, status=exc.status_code)
            continue
        log.recording_sid = ""
        removed += 1
    if removed:
        await session.commit()
    return removed


async def run(tick: float = SWEEP_SECONDS) -> None:
    from app.db.session import AsyncSessionLocal

    while True:
        if get_settings().recording_purge and telnyx.configured():
            try:
                async with AsyncSessionLocal() as session:
                    removed = await purge_once(session)
                if removed:
                    await logger.ainfo("recordings_purged", count=removed)
            except Exception as exc:  # noqa: BLE001 — try again next round
                await logger.awarning("recording_purge_sweep_failed", error=str(exc)[:200])
        await asyncio.sleep(tick)


__all__ = ["DEFAULT_DAYS", "EXTENDED_DAYS", "ensure_available", "expired", "purge_once", "retention_days", "run"]
