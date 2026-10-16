"""Admin add-ons: set an account's add-on set directly, and decide owners' add-on requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.routes.admin.common import _addon_request, _merchant_or_404, _merchants, account_editors, admin_out
from app.core.addons import CATALOG, MAX_QUANTITY, entitlements, quantities, stored
from app.core.datetime_utils import utcnow
from app.db.session import get_db
from app.models import AddonRequest, Merchant

router = APIRouter()


class AddonsUpdate(BaseModel):
    #: The account's complete add-on set: {key: quantity}; missing keys are removed.
    addons: dict[str, int] = Field(default_factory=dict)


@router.put("/merchants/{merchant_id}/addons")
async def set_addons(merchant_id: str, data: AddonsUpdate, _: dict = Depends(account_editors), db: AsyncSession = Depends(get_db)):
    merchant = await _merchant_or_404(db, merchant_id)
    unknown = sorted(set(data.addons) - set(CATALOG))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown add-on: {', '.join(unknown)}")
    if any(qty < 0 or qty > MAX_QUANTITY for qty in data.addons.values()):
        raise HTTPException(status_code=422, detail=f"Quantities must be between 0 and {MAX_QUANTITY}")
    merchant.addons = stored(data.addons)
    _sync_channels(merchant)
    await db.commit()
    await db.refresh(merchant)
    return {"merchant": admin_out(merchant).model_dump(mode="json"), "entitlements": entitlements(merchant).as_json()}


def _sync_channels(merchant: Merchant) -> None:
    """Losing the website chat switches the widget off (and turning it on is the owner's call)."""
    from app.core.plans import CHANNEL_WEB_CHAT

    if merchant.widget_enabled and not entitlements(merchant).has_channel(CHANNEL_WEB_CHAT):
        merchant.widget_enabled = False


@router.get("/addon-requests")
async def list_addon_requests(
    status: str = Query(default="pending"),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AddonRequest)
    if status and status != "all":
        stmt = stmt.where(AddonRequest.status == status)
    rows = list(await db.scalars(stmt.order_by(AddonRequest.created_at.desc()).limit(200)))
    merchants = await _merchants(db, {row.merchant_id for row in rows})
    return {"items": [_addon_request(row, merchants.get(row.merchant_id)) for row in rows]}


class AddonDecision(BaseModel):
    admin_note: str = Field(default="", max_length=500)


@router.post("/addon-requests/{request_id}/{decision}")
async def decide_addon_request(
    request_id: str, decision: str, data: AddonDecision, _: dict = Depends(account_editors), db: AsyncSession = Depends(get_db)
):
    if decision not in ("approve", "decline"):
        raise HTTPException(status_code=404, detail="Unknown action")
    row = await db.get(AddonRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="This request was already handled")
    merchant = await _merchant_or_404(db, row.merchant_id)
    if decision == "approve":
        addon = CATALOG.get(row.addon)
        if addon is None:
            raise HTTPException(status_code=422, detail="That add-on no longer exists")
        owned = quantities(merchant.addons)
        owned[addon.key] = min(MAX_QUANTITY, owned.get(addon.key, 0) + row.quantity) if addon.stackable else 1
        merchant.addons = stored(owned)
        row.status = "approved"
    else:
        row.status = "declined"
    row.admin_note = data.admin_note.strip()
    row.decided_at = utcnow()
    await db.commit()
    return _addon_request(row, merchant)
