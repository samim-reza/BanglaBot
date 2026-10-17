"""The account's phone line: owners can't buy numbers themselves — they ask, the admin assigns one.

The ask is an add-on request row (``addon = "phone_line"``) so it lands in the admin's
add-on request queue; approving it changes no add-ons and needs the number assigned first.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.addons import entitlements
from app.core.plans import CHANNEL_VOICE
from app.db.session import get_db
from app.models import AddonRequest, Merchant
from app.models.addon_request import PHONE_LINE

router = APIRouter(prefix="/api/phone-line", tags=["channels"])


class PhoneLineRequestIn(BaseModel):
    #: e.g. a preferred area code.
    note: str = Field(default="", max_length=300)


async def _latest(db: AsyncSession, merchant: Merchant) -> AddonRequest | None:
    return await db.scalar(
        select(AddonRequest)
        .where(AddonRequest.merchant_id == merchant.id, AddonRequest.addon == PHONE_LINE)
        .order_by(AddonRequest.created_at.desc())
        .limit(1)
    )


def _view(merchant: Merchant, row: AddonRequest | None) -> dict[str, Any]:
    request = None
    if row is not None:
        request = {"id": row.id, "status": row.status, "note": row.note, "admin_note": row.admin_note, "created_at": row.created_at, "decided_at": row.decided_at}
    return {"number": (merchant.inbound_number or "").strip(), "request": request}


@router.get("")
async def phone_line(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return _view(merchant, await _latest(db, merchant))


@router.post("/request", status_code=201)
async def request_number(data: PhoneLineRequestIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    if not entitlements(merchant).has_channel(CHANNEL_VOICE):
        raise HTTPException(status_code=403, detail="Phone calls aren't part of your plan")
    if (merchant.inbound_number or "").strip():
        raise HTTPException(status_code=409, detail="You already have a phone number")
    row = await _latest(db, merchant)
    if row is not None and row.status == "pending":
        row.note = data.note.strip() or row.note
    else:
        row = AddonRequest(merchant_id=merchant.id, addon=PHONE_LINE, quantity=1, note=data.note.strip(), status="pending")
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return _view(merchant, row)
