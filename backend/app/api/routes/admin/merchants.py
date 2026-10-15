"""Admin account management: list / create / view / update / delete accounts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.api.routes.admin.common import _addon_request, _merchant_or_404, admin_out
from app.api.routes.auth import apply_settings
from app.core.addons import entitlements
from app.core.plans import PLANS
from app.core.regions import normalize_phone, region_defaults
from app.core.security import hash_password
from app.db.session import get_db
from app.models import AddonRequest, CallLog, CatalogItem, Merchant, Order, OrderStatus
from app.schemas.admin import MerchantAdminUpdate, MerchantCreate
from app.schemas.merchant import MerchantOut
from app.services import audit_service, auth_service, channel_service, usage_service
from app.verticals import get_vertical

router = APIRouter()


async def _inbound_taken(db: AsyncSession, number: str, merchant_id: str | None = None) -> bool:
    if not number:
        return False
    target = normalize_phone(number, "INTL")
    rows = await db.execute(select(Merchant.id, Merchant.inbound_number, Merchant.region).where(Merchant.inbound_number != ""))
    for other_id, other_number, region in rows:
        if other_id != merchant_id and normalize_phone(other_number, region) == target:
            return True
    return False


@router.get("/merchants", response_model=list[MerchantOut])
async def list_merchants(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(Merchant).order_by(Merchant.created_at.desc()))
    return [admin_out(row) for row in rows]


@router.post("/merchants", response_model=MerchantOut, status_code=201)
async def create_merchant(data: MerchantCreate, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    auth_service.require_password_policy(data.password, username=data.username, email=data.email)
    exists = await db.scalar(select(Merchant.id).where(Merchant.username == data.username.strip()))
    if exists:
        raise HTTPException(status_code=409, detail="Username is already taken")
    inbound = normalize_phone(data.inbound_number, data.region) if data.inbound_number.strip() else ""
    if inbound and await _inbound_taken(db, inbound):
        raise HTTPException(status_code=409, detail="That inbound number already belongs to another account")
    preset = region_defaults(data.region)
    vertical = get_vertical(data.vertical)
    merchant = Merchant(
        business_name=data.business_name.strip(),
        username=data.username.strip(),
        password_hash=hash_password(data.password),
        owner_name=data.owner_name.strip(),
        phone=data.phone.strip(),
        email=data.email.strip(),
        support_phone=data.support_phone.strip(),
        vertical=vertical.key,
        vertical_config={},
        knowledge="",
        inbound_number=inbound,
        region=preset["region"],
        timezone=(data.timezone or preset["timezone"]).strip(),
        currency=(data.currency or preset["currency"]).strip().upper(),
        emergency_number=(data.emergency_number or preset["emergency_number"]).strip(),
        language=data.language,
        supported_languages=[data.language] + [code for code in ("en", "bn") if code != data.language],
        voice_persona=data.voice_persona,
        plan=data.plan if data.plan in PLANS else "trial",
        widget_settings={},
    )
    db.add(merchant)
    await db.commit()
    await db.refresh(merchant)
    return admin_out(merchant)


@router.get("/merchants/{merchant_id}")
async def get_merchant(merchant_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    merchant = await _merchant_or_404(db, merchant_id)
    catalog = int(await db.scalar(select(func.count(CatalogItem.id)).where(CatalogItem.merchant_id == merchant.id)) or 0)
    records = int(await db.scalar(select(func.count(Order.id)).where(Order.merchant_id == merchant.id)) or 0)
    requests = await db.scalars(
        select(AddonRequest).where(AddonRequest.merchant_id == merchant.id).order_by(AddonRequest.created_at.desc()).limit(20)
    )
    return {
        "merchant": admin_out(merchant).model_dump(mode="json"),
        "usage": await usage_service.month_usage(db, merchant),
        "entitlements": entitlements(merchant).as_json(),
        "addon_requests": [_addon_request(row, merchant) for row in requests],
        "catalog_items": catalog,
        "records": records,
        "provider_settings": dict(getattr(merchant, "provider_settings", None) or {}),
    }


@router.patch("/merchants/{merchant_id}", response_model=MerchantOut)
async def update_merchant(
    merchant_id: str,
    data: MerchantAdminUpdate,
    request: Request,
    admin: AdminPrincipal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    merchant = await _merchant_or_404(db, merchant_id)
    changes = data.model_dump(exclude_unset=True)
    admin_only = {
        key: changes.pop(key) for key in ("password", "active", "plan", "region", "inbound_number", "whatsapp_number") if key in changes
    }
    apply_settings(merchant, MerchantAdminUpdate.model_validate(changes))
    if admin_only.get("password"):
        auth_service.check_new_password(merchant, admin_only["password"])
        merchant.password_hash = hash_password(admin_only["password"])
        auth_service.revoke_sessions(merchant)
        audit_service.stage(
            db, action="merchant.password_changed", **admin.audit_actor, target_type="merchant",
            target_id=merchant.id, merchant_id=merchant.id, request=request,
        )
    if admin_only.get("active") is not None:
        merchant.active = bool(admin_only["active"])
    if admin_only.get("plan"):
        merchant.plan = admin_only["plan"]
    if admin_only.get("region"):
        merchant.region = admin_only["region"]
    if "inbound_number" in admin_only and admin_only["inbound_number"] is not None:
        raw = str(admin_only["inbound_number"]).strip()
        number = normalize_phone(raw, merchant.region) if raw else ""
        if number and await _inbound_taken(db, number, merchant.id):
            raise HTTPException(status_code=409, detail="That inbound number already belongs to another account")
        merchant.inbound_number = number
    if admin_only.get("whatsapp_number") is not None:
        raw = str(admin_only["whatsapp_number"]).strip()
        number = normalize_phone(raw, merchant.region) if raw else ""
        if number and await _whatsapp_taken(db, number, merchant.id):
            raise HTTPException(status_code=409, detail="That WhatsApp number already belongs to another account")
        config = channel_service.settings_of(merchant)
        config["whatsapp"] = {**(config.get("whatsapp") or {}), "number": number}
        merchant.channel_settings = config
    await db.commit()
    await db.refresh(merchant)
    return admin_out(merchant)


async def _whatsapp_taken(db: AsyncSession, number: str, merchant_id: str) -> bool:
    owner = await db.scalar(
        select(Merchant.id).where(Merchant.channel_settings["whatsapp"]["number"].astext == number, Merchant.id != merchant_id)
    )
    return owner is not None


@router.delete("/merchants/{merchant_id}", status_code=204)
async def delete_merchant(merchant_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    merchant = await _merchant_or_404(db, merchant_id)
    calling = await db.scalar(
        select(func.count(Order.id)).where(Order.merchant_id == merchant.id, Order.status == OrderStatus.calling)
    )
    if calling:
        raise HTTPException(status_code=409, detail="This account has a call in progress")
    for log in await db.scalars(select(CallLog).where(CallLog.merchant_id == merchant.id)):
        await db.delete(log)
    for order in await db.scalars(select(Order).where(Order.merchant_id == merchant.id)):
        await db.delete(order)
    for item in await db.scalars(select(CatalogItem).where(CatalogItem.merchant_id == merchant.id)):
        await db.delete(item)
    await db.delete(merchant)
    await db.commit()
    return Response(status_code=204)
