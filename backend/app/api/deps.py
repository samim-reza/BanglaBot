"""FastAPI dependencies: the logged-in merchant, or the platform admin."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import bearer_payload, require_roles
from app.db.session import get_db
from app.models import Merchant

MERCHANT_ROLE = "merchant"
ADMIN_ROLE = "admin"


async def get_current_merchant(
    payload: dict = Depends(bearer_payload),
    db: AsyncSession = Depends(get_db),
) -> Merchant:
    require_roles(payload, {MERCHANT_ROLE})
    merchant = await db.get(Merchant, str(payload.get("sub") or ""))
    if merchant is None:
        raise HTTPException(status_code=401, detail="Merchant account not found")
    if not merchant.active:
        raise HTTPException(status_code=403, detail="Merchant account is disabled")
    return merchant


async def require_admin(payload: dict = Depends(bearer_payload)) -> dict:
    require_roles(payload, {ADMIN_ROLE})
    return payload
