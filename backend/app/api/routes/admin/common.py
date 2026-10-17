"""Helpers shared by the admin route modules: the admin view of an account, lookups."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.routes.auth import merchant_out
from app.core.addons import CATALOG
from app.core.security import ROLE_SUPERADMIN, ROLE_SUPPORT
from app.models import AddonRequest, Merchant
from app.models.addon_request import PHONE_LINE, PHONE_LINE_LABEL
from app.schemas.merchant import MerchantOut


#: Changing accounts (create / edit / add-ons / requests / inquiries); finance only reads.
account_editors = require_admin(ROLE_SUPERADMIN, ROLE_SUPPORT)
superadmin_only = require_admin(ROLE_SUPERADMIN)


def admin_out(merchant: Merchant) -> MerchantOut:
    """An account as the admin sees it — without the owner's webhook signing secret."""
    out = merchant_out(merchant)
    return out.model_copy(update={"webhook_secret": ""})


async def _merchant_or_404(db: AsyncSession, merchant_id: str) -> Merchant:
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return merchant


async def _merchants(db: AsyncSession, ids: set[str]) -> dict[str, Merchant]:
    if not ids:
        return {}
    return {row.id: row for row in await db.scalars(select(Merchant).where(Merchant.id.in_(ids)))}


def _addon_request(row: AddonRequest, merchant: Merchant | None) -> dict:
    addon = CATALOG.get(row.addon)
    return {
        "id": row.id,
        "merchant_id": row.merchant_id,
        "merchant_name": merchant.business_name if merchant else "",
        "merchant_plan": merchant.plan if merchant else "",
        "addon": row.addon,
        "addon_name": addon.name if addon else (PHONE_LINE_LABEL if row.addon == PHONE_LINE else row.addon),
        "price_label": addon.price_label() if addon else "",
        "quantity": row.quantity,
        "note": row.note,
        "status": row.status,
        "admin_note": row.admin_note,
        "created_at": row.created_at,
        "decided_at": row.decided_at,
    }
