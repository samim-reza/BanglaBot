"""Read / write ``platform_settings`` rows (one JSON value per key).

Generic: the finance engine keeps its price book and spend caps here, billing
its plan catalog. Writers stage the change in the caller's session; the caller
commits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.models.platform_setting import PlatformSetting

MAX_KEY_CHARS = 80


async def get_value(db: AsyncSession, key: str, default: Any = None) -> Any:
    row = await db.get(PlatformSetting, key)
    if row is None or row.value is None:
        return default
    return row.value


async def put_value(db: AsyncSession, key: str, value: Any, *, updated_by: str = "") -> PlatformSetting:
    if not key or len(key) > MAX_KEY_CHARS:
        raise ValueError("bad settings key")
    row = await db.get(PlatformSetting, key)
    if row is None:
        row = PlatformSetting(key=key, value=value, updated_by=str(updated_by or "")[:80], updated_at=utcnow())
        db.add(row)
    else:
        row.value = value
        row.updated_by = str(updated_by or "")[:80]
        row.updated_at = utcnow()
    return row


__all__ = ["get_value", "put_value"]
