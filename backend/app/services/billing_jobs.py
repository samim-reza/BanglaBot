"""Background upkeep for billing, started from the app lifespan:

* refresh the installed tier / add-on catalog from ``platform_settings`` (every
  ``catalog_plans.REFRESH_SECONDS``), so admin edits reach every worker;
* sweep subscriptions whose period ended (past due / cancelled / scheduled
  downgrades) every ``SWEEP_SECONDS``.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.services import catalog_plans, subscription_service

logger = structlog.get_logger(__name__)

SWEEP_SECONDS = 900.0


async def sweep_once() -> dict[str, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        counts = await subscription_service.sweep(session)
        await session.commit()
    if any(counts.values()):
        await logger.ainfo("subscriptions_swept", **counts)
    return counts


async def run(tick: float = catalog_plans.REFRESH_SECONDS) -> None:
    last_sweep = 0.0
    while True:
        await catalog_plans.ensure_fresh(max_age=0)
        if time.monotonic() - last_sweep >= SWEEP_SECONDS:
            last_sweep = time.monotonic()
            try:
                await sweep_once()
            except Exception as exc:  # noqa: BLE001 — try again next round
                await logger.awarning("subscription_sweep_failed", error=str(exc)[:200])
        await asyncio.sleep(tick)


__all__ = ["run", "sweep_once"]
