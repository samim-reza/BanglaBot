"""Admin impersonation: a short-lived owner session for an account's portal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.api.routes.admin.common import _merchant_or_404
from app.api.routes.auth import merchant_out
from app.core.security import issue_merchant_token
from app.db.session import get_db
from app.services import audit_service

router = APIRouter()


@router.post("/merchants/{merchant_id}/impersonate")
async def impersonate(
    merchant_id: str,
    request: Request,
    admin: AdminPrincipal = Depends(require_admin("superadmin", "support")),
    db: AsyncSession = Depends(get_db),
):
    """A short-lived (2 h) owner session so the admin can see / set up an account's portal."""
    merchant = await _merchant_or_404(db, merchant_id)
    if not merchant.active:
        raise HTTPException(status_code=409, detail="This account is disabled — activate it first")
    token = issue_merchant_token(merchant, impersonated_by=admin.id)
    await audit_service.record(
        action="admin.impersonate", **admin.audit_actor, target_type="merchant", target_id=merchant.id,
        merchant_id=merchant.id, request=request,
    )
    return {"token": token, "merchant": merchant_out(merchant).model_dump(mode="json")}
