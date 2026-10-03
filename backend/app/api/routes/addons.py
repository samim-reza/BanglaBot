"""The account's add-on shop: what the plan includes, what is active, what can be requested.

There is no online payment yet: a request lands with the platform admin, who
turns the add-on on (``/api/admin/addon-requests``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.addons import CATALOG, MAX_QUANTITY, available_for, entitlements, public_catalog
from app.db.session import get_db
from app.models import AddonRequest, Merchant

router = APIRouter(prefix="/api/addons", tags=["addons"])

OPEN = "pending"


def request_out(row: AddonRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "addon": row.addon,
        "quantity": row.quantity,
        "note": row.note,
        "status": row.status,
        "admin_note": row.admin_note,
        "created_at": row.created_at,
        "decided_at": row.decided_at,
    }


async def shop(db: AsyncSession, merchant: Merchant) -> dict[str, Any]:
    ent = entitlements(merchant)
    rows = await db.scalars(
        select(AddonRequest).where(AddonRequest.merchant_id == merchant.id).order_by(AddonRequest.created_at.desc()).limit(20)
    )
    return {
        "catalog": public_catalog(),
        "available": available_for(merchant),
        "entitlements": ent.as_json(),
        "plan": ent.plan.as_json(),
        "requests": [request_out(row) for row in rows],
    }


@router.get("")
async def get_shop(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await shop(db, merchant)


class AddonRequestIn(BaseModel):
    addon: str = Field(min_length=1, max_length=32)
    quantity: int = Field(default=1, ge=1, le=MAX_QUANTITY)
    note: str = Field(default="", max_length=500)


@router.post("/requests", status_code=201)
async def request_addon(data: AddonRequestIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    addon = CATALOG.get(data.addon)
    if addon is None or addon.key not in available_for(merchant):
        raise HTTPException(status_code=422, detail="That add-on isn't available for your plan")
    if not addon.stackable and addon.key in entitlements(merchant).addons:
        raise HTTPException(status_code=409, detail="You already have this add-on")
    quantity = data.quantity if addon.stackable else 1
    pending = await db.scalar(
        select(AddonRequest).where(
            AddonRequest.merchant_id == merchant.id, AddonRequest.addon == addon.key, AddonRequest.status == OPEN
        )
    )
    if pending is not None:
        pending.quantity, pending.note = quantity, data.note.strip()
    else:
        db.add(AddonRequest(merchant_id=merchant.id, addon=addon.key, quantity=quantity, note=data.note.strip(), status=OPEN))
    await db.commit()
    return await shop(db, merchant)


@router.delete("/requests/{request_id}")
async def cancel_request(request_id: str, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    row = await db.get(AddonRequest, request_id)
    if row is None or row.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.status != OPEN:
        raise HTTPException(status_code=409, detail="This request was already handled")
    row.status = "cancelled"
    await db.commit()
    return await shop(db, merchant)
