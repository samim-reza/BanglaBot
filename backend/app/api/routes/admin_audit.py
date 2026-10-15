"""The audit log for the admin console: newest first, cursor-paginated, filterable."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.core.security import ROLE_SUPERADMIN, ROLE_SUPPORT
from app.db.session import get_db
from app.services import audit_service

router = APIRouter(prefix="/api/admin/audit", tags=["admin-audit"])


@router.get("")
async def list_audit_events(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str = Query(default="", max_length=200),
    action: str = Query(default="", max_length=64, description='Exact action, or a prefix ending in "*" (e.g. "admin.*")'),
    merchant_id: str = Query(default="", max_length=64),
    actor: str = Query(default="", max_length=80, description="actor_id (an admin user id, env:<name>, or a merchant id)"),
    actor_type: str = Query(default="", pattern="^(|admin|merchant|system)$"),
    _: AdminPrincipal = Depends(require_admin(ROLE_SUPERADMIN, ROLE_SUPPORT)),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await audit_service.list_events(
            db, limit=limit, cursor=cursor, action=action, merchant_id=merchant_id, actor=actor, actor_type=actor_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc
