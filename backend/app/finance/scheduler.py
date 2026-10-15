"""Finance background jobs: SMS metering, cost-guard refresh, ledger retention.

``run_scheduler`` is a lifespan task; each job runs in its own session and a
failing job never stops the others or the loop.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

import structlog

from app.finance import guard, ledger, sms_meter
from app.finance.config import get_finance_settings

logger = structlog.get_logger(__name__)

#: Session factory (tests swap in a fake).
session_factory: Any = None
_last_prune: date | None = None


def sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


async def _job(name: str, work) -> Any:  # noqa: ANN001
    try:
        async with sessions()() as session:
            return await work(session)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — one job's failure never stops the rest
        await logger.awarning("finance_job_failed", job=name, error=str(exc)[:200], error_type=type(exc).__name__)
        return None


async def _prune(session: Any) -> int:
    deleted = await ledger.prune(session, retention_days=int(get_finance_settings().finance_event_retention_days))
    await session.commit()
    return deleted


async def run_jobs(now: datetime | None = None) -> dict[str, Any]:
    global _last_prune
    stamp = now or datetime.now(timezone.utc)
    out: dict[str, Any] = {
        "sms": await _job("sms_meter", lambda session: sms_meter.meter_sent_sms(session, now=stamp)),
        "guard": await _job("guard_refresh", guard.refresh),
    }
    if _last_prune != stamp.date():
        out["pruned"] = await _job("ledger_prune", _prune)
        _last_prune = stamp.date()
    return out


async def run_scheduler(interval: float | None = None) -> None:
    every = max(30.0, float(interval or get_finance_settings().finance_job_interval_seconds))
    await asyncio.sleep(5)
    while True:
        await run_jobs()
        await asyncio.sleep(every)


__all__ = ["run_jobs", "run_scheduler"]
