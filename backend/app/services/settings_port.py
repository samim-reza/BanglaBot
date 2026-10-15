"""Port to the generic ``platform_settings`` key/value table, for the plan catalog keys.

The table and its model (``app.models.platform_setting.PlatformSetting``: key PK,
value JSONB, updated_at, updated_by) belong to the finance workstream. Values
written here are always JSON objects (``{"tiers": [...]}``, ``{"enabled": true}``).
The model is imported lazily: without it reads fall back to defaults and writes
answer 503.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow

logger = structlog.get_logger(__name__)

#: Session factory for reads outside a request (tests swap in a fake).
session_factory: Any = None


class SettingsUnavailable(RuntimeError):
    """The platform_settings model isn't installed yet."""


def model() -> Any:
    try:
        from app.models.platform_setting import PlatformSetting  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SettingsUnavailable("platform_settings is not available") from exc
    return PlatformSetting


def _sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


async def get_many(keys: list[str], *, db: AsyncSession | None = None) -> dict[str, Any]:
    """``{key: value}`` for the keys that are set (missing keys are left out)."""
    try:
        Setting = model()
    except SettingsUnavailable:
        return {}
    if db is not None:
        return await _read(db, Setting, keys)
    async with _sessions()() as session:
        return await _read(session, Setting, keys)


async def _read(db: Any, Setting: Any, keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        row = await db.get(Setting, key)
        if row is not None and row.value is not None:
            out[key] = row.value
    return out


async def get(key: str, default: Any = None, *, db: AsyncSession | None = None) -> Any:
    return (await get_many([key], db=db)).get(key, default)


async def put(db: AsyncSession, key: str, value: Any, *, by: str = "") -> None:
    """Stage ``key = value`` on ``db`` (the caller commits)."""
    try:
        Setting = model()
    except SettingsUnavailable as exc:
        raise HTTPException(status_code=503, detail="Settings storage isn't ready yet") from exc
    row = await db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    if hasattr(row, "updated_by"):
        row.updated_by = str(by or "")[:80]
    if hasattr(row, "updated_at"):
        row.updated_at = utcnow()


async def delete(db: AsyncSession, key: str) -> None:
    try:
        Setting = model()
    except SettingsUnavailable:
        return
    row = await db.get(Setting, key)
    if row is not None:
        await db.delete(row)


__all__ = ["SettingsUnavailable", "delete", "get", "get_many", "put"]
