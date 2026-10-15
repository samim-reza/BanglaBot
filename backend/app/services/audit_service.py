"""Audit log: who did what, when, from where.

- ``await record(action=..., actor_type=..., actor_id=..., ...)`` writes one event in
  its own session and never raises into the request (a failed write is logged).
- ``stage(db, ...)`` adds the event to the caller's session instead, so it commits
  (or rolls back) together with the change it describes.
- ``list_events`` pages newest-first by ``(at, id)`` with an opaque cursor.

``meta`` is kept under 2 KB and keys that look secret are masked.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import Request
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import decode_cursor, encode_cursor, page_size
from app.core.ratelimit.ip import client_ip
from app.models.audit_event import AuditEvent

logger = structlog.get_logger(__name__)

ACTOR_ADMIN = "admin"
ACTOR_MERCHANT = "merchant"
ACTOR_SYSTEM = "system"
ACTOR_TYPES = (ACTOR_ADMIN, ACTOR_MERCHANT, ACTOR_SYSTEM)
MAX_META_BYTES = 2048
_SENSITIVE = ("password", "secret", "token", "totp", "authorization", "api_key", "apikey", "signature")
_SENSITIVE_EXACT = ("code", "otp", "pin")

#: Session factory for ``record`` (tests swap in a fake).
session_factory: Any = None


def _sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


def _sensitive(key: Any) -> bool:
    name = str(key).lower()
    return name in _SENSITIVE_EXACT or any(word in name for word in _SENSITIVE)


def _mask(value: Any, depth: int = 0) -> Any:
    if isinstance(value, dict) and depth < 3:
        return {
            str(key): ("***" if _sensitive(key) and value[key] not in (None, "") else _mask(value[key], depth + 1))
            for key in list(value)[:50]
        }
    if isinstance(value, (list, tuple)) and depth < 3:
        return [_mask(item, depth + 1) for item in list(value)[:50]]
    return value


def clean_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    encoded = json.dumps(_mask(dict(meta)), default=str, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= MAX_META_BYTES:
        return json.loads(encoded)
    preview = encoded.encode("utf-8")[: MAX_META_BYTES - 200].decode("utf-8", "ignore")
    return {"truncated": True, "preview": preview}


def build_event(
    *,
    action: str,
    actor_type: str = ACTOR_SYSTEM,
    actor_id: str = "",
    target_type: str = "",
    target_id: str = "",
    merchant_id: str | None = None,
    ip: str = "",
    request: Request | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditEvent:
    if request is not None and not ip:
        ip = client_ip(request)
    return AuditEvent(
        actor_type=actor_type if actor_type in ACTOR_TYPES else ACTOR_SYSTEM,
        actor_id=str(actor_id or "")[:80],
        action=str(action)[:64],
        target_type=str(target_type or "")[:32],
        target_id=str(target_id or "")[:80],
        merchant_id=str(merchant_id) if merchant_id else None,
        ip=str(ip or "")[:64],
        meta=clean_meta(meta),
    )


async def record(**fields: Any) -> None:
    """Write one event in its own transaction; best-effort, never raises."""
    try:
        event = build_event(**fields)
        async with _sessions()() as session:
            session.add(event)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — auditing never breaks the request it describes
        await logger.awarning("audit_record_failed", action=fields.get("action"), error=str(exc)[:200])


def stage(db: AsyncSession, **fields: Any) -> None:
    """Add the event to ``db``: it commits with the caller's change. Never raises."""
    try:
        db.add(build_event(**fields))
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_stage_failed", action=fields.get("action"), error=str(exc)[:200])


def serialize(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "at": event.at,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "merchant_id": event.merchant_id,
        "ip": event.ip,
        "meta": event.meta or {},
    }


def filtered(stmt: Any, *, action: str = "", merchant_id: str = "", actor: str = "", actor_type: str = "") -> Any:
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action[:-1]) if action.endswith("*") else AuditEvent.action == action)
    if merchant_id:
        stmt = stmt.where(AuditEvent.merchant_id == merchant_id)
    if actor:
        stmt = stmt.where(AuditEvent.actor_id == actor)
    if actor_type:
        stmt = stmt.where(AuditEvent.actor_type == actor_type)
    return stmt


async def _actor_names(db: AsyncSession, rows: list[AuditEvent]) -> dict[tuple[str, str], str]:
    """Readable names for the page's actors: admin usernames and business names (one query each)."""
    from app.models import Merchant
    from app.models.admin_user import AdminUser

    names: dict[tuple[str, str], str] = {}
    admin_ids = {row.actor_id for row in rows if row.actor_type == ACTOR_ADMIN and row.actor_id and not row.actor_id.startswith("env:")}
    merchant_ids = {row.actor_id for row in rows if row.actor_type == ACTOR_MERCHANT and row.actor_id}
    if admin_ids:
        for row_id, username in await db.execute(select(AdminUser.id, AdminUser.username).where(AdminUser.id.in_(admin_ids))):
            names[(ACTOR_ADMIN, row_id)] = username
    if merchant_ids:
        for row_id, business in await db.execute(select(Merchant.id, Merchant.business_name).where(Merchant.id.in_(merchant_ids))):
            names[(ACTOR_MERCHANT, row_id)] = business
    for row in rows:
        if row.actor_type == ACTOR_ADMIN and row.actor_id.startswith("env:"):
            names[(ACTOR_ADMIN, row.actor_id)] = row.actor_id[4:]
    return names


async def list_events(db: AsyncSession, *, limit: int = 50, cursor: str = "", **filters: str) -> dict[str, Any]:
    """Newest first. Raises ``ValueError`` for a malformed cursor."""
    size = page_size(limit)
    stmt = filtered(select(AuditEvent), **filters)
    if cursor:
        at, row_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(AuditEvent.at, AuditEvent.id) < tuple_(at, row_id))
    rows = list(await db.scalars(stmt.order_by(AuditEvent.at.desc(), AuditEvent.id.desc()).limit(size + 1)))
    more = len(rows) > size
    rows = rows[:size]
    try:
        names = await _actor_names(db, rows)
    except Exception:  # noqa: BLE001 — names are cosmetic; the log itself must always load
        names = {}
    return {
        "items": [{**serialize(row), "actor_name": names.get((row.actor_type, row.actor_id), "")} for row in rows],
        "next_cursor": encode_cursor(rows[-1].at, rows[-1].id) if more and rows else None,
    }


__all__ = [
    "ACTOR_ADMIN",
    "ACTOR_MERCHANT",
    "ACTOR_SYSTEM",
    "build_event",
    "clean_meta",
    "list_events",
    "record",
    "serialize",
    "stage",
]
