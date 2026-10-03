"""Platform admin: login from settings, accounts CRUD, cross-account views, sales inquiries."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLE, require_admin
from app.api.routes.auth import apply_settings, merchant_out
from app.core.config import get_settings
from app.core.datetime_utils import today_bounds_utc
from app.core.addons import CATALOG, MAX_QUANTITY, entitlements, quantities, stored
from app.core.datetime_utils import utcnow
from app.core.plans import PLANS
from app.core.regions import normalize_phone, region_defaults, regions_json
from app.core.security import hash_password, sign_token
from app.db.session import get_db
from app.models import AddonRequest, CallLog, CatalogItem, Merchant, Order, OrderStatus, SalesInquiry
from app.schemas.admin import (
    AdminCallPage,
    AdminLoginRequest,
    AdminOrderPage,
    AdminOverview,
    AdminTokenResponse,
    MerchantAdminUpdate,
    MerchantCreate,
)
from app.schemas.merchant import MerchantOut
from app.services import channel_service, order_service, usage_service
from app.verticals import VERTICALS, get_vertical

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_out(merchant: Merchant) -> MerchantOut:
    """An account as the admin sees it — without the owner's webhook signing secret."""
    out = merchant_out(merchant)
    return out.model_copy(update={"webhook_secret": ""})


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(data: AdminLoginRequest):
    settings = get_settings()
    username_ok = hmac.compare_digest(data.username.strip(), settings.admin_username)
    password_ok = hmac.compare_digest(data.password, settings.admin_password)
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return AdminTokenResponse(token=sign_token({"sub": settings.admin_username, "role": ADMIN_ROLE}))


@router.get("/meta")
async def meta(_: dict = Depends(require_admin)):
    """Choices for the account forms: business engines, regions, plans, languages."""
    return {
        "verticals": [v.as_json() for v in VERTICALS.values()],
        "regions": regions_json(),
        "plans": [plan.as_json() for plan in PLANS.values()],
        "languages": [{"code": "en", "label": "English"}, {"code": "bn", "label": "Bangla (বাংলা)"}],
    }


@router.get("/overview", response_model=AdminOverview)
async def overview(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    start, end = today_bounds_utc()

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    today_calls = CallLog.created_at >= start, CallLog.created_at < end
    by_vertical = {key: 0 for key in VERTICALS}
    for vertical, total in await db.execute(select(Merchant.vertical, func.count(Merchant.id)).group_by(Merchant.vertical)):
        by_vertical[str(vertical or "ecommerce")] = int(total)
    return AdminOverview(
        merchants=await count(select(func.count(Merchant.id))),
        active_merchants=await count(select(func.count(Merchant.id)).where(Merchant.active.is_(True))),
        orders=await count(select(func.count(Order.id))),
        calls_today=await count(select(func.count(CallLog.id)).where(*today_calls)),
        confirmed_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.outcome == "confirmed")),
        cancelled_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.outcome == "cancelled")),
        orders_today=await count(select(func.count(Order.id)).where(Order.created_at >= start, Order.created_at < end)),
        pending_orders=await count(select(func.count(Order.id)).where(Order.status == OrderStatus.pending)),
        calling_orders=await count(select(func.count(Order.id)).where(Order.status == OrderStatus.calling)),
        needs_review_orders=await count(select(func.count(Order.id)).where(Order.status == OrderStatus.needs_review)),
        inbound_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.direction == "inbound")),
        booked_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.outcome == "booked")),
        by_vertical=by_vertical,
        pending_addon_requests=await count(select(func.count(AddonRequest.id)).where(AddonRequest.status == "pending")),
    )


# ------------------------------------------------------------------ accounts
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


async def _merchant_or_404(db: AsyncSession, merchant_id: str) -> Merchant:
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return merchant


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
    }


@router.patch("/merchants/{merchant_id}", response_model=MerchantOut)
async def update_merchant(
    merchant_id: str, data: MerchantAdminUpdate, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    merchant = await _merchant_or_404(db, merchant_id)
    changes = data.model_dump(exclude_unset=True)
    admin_only = {
        key: changes.pop(key) for key in ("password", "active", "plan", "region", "inbound_number", "whatsapp_number") if key in changes
    }
    apply_settings(merchant, MerchantAdminUpdate.model_validate(changes))
    if admin_only.get("password"):
        merchant.password_hash = hash_password(admin_only["password"])
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


# ------------------------------------------------------------------ add-ons
class AddonsUpdate(BaseModel):
    #: The account's complete add-on set: {key: quantity}; missing keys are removed.
    addons: dict[str, int] = Field(default_factory=dict)


@router.put("/merchants/{merchant_id}/addons")
async def set_addons(merchant_id: str, data: AddonsUpdate, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
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


def _addon_request(row: AddonRequest, merchant: Merchant | None) -> dict:
    addon = CATALOG.get(row.addon)
    return {
        "id": row.id,
        "merchant_id": row.merchant_id,
        "merchant_name": merchant.business_name if merchant else "",
        "merchant_plan": merchant.plan if merchant else "",
        "addon": row.addon,
        "addon_name": addon.name if addon else row.addon,
        "price_label": addon.price_label() if addon else "",
        "quantity": row.quantity,
        "note": row.note,
        "status": row.status,
        "admin_note": row.admin_note,
        "created_at": row.created_at,
        "decided_at": row.decided_at,
    }


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
    request_id: str, decision: str, data: AddonDecision, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)
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


@router.post("/merchants/{merchant_id}/impersonate")
async def impersonate(merchant_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """A short-lived owner session so the admin can see / set up an account's portal."""
    from app.api.deps import MERCHANT_ROLE

    merchant = await _merchant_or_404(db, merchant_id)
    if not merchant.active:
        raise HTTPException(status_code=409, detail="This account is disabled — activate it first")
    token = sign_token({"sub": merchant.id, "role": MERCHANT_ROLE, "username": merchant.username, "imp": True}, ttl_seconds=2 * 3600)
    return {"token": token, "merchant": merchant_out(merchant).model_dump(mode="json")}


# ------------------------------------------------------------------ records / calls
@router.get("/orders", response_model=AdminOrderPage)
async def admin_orders(
    merchant_id: str = Query(default=""),
    status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await order_service.list_orders(
        db,
        merchant_id=merchant_id or None,
        status=order_service.parse_status(status),
        search="",
        page=page,
        page_size=page_size,
    )
    merchants = await _merchants(db, {row.merchant_id for row in rows})
    names = await order_service.catalog_names(db, {str(row.catalog_item_id or "") for row in rows})
    items = []
    for row in rows:
        merchant = merchants.get(row.merchant_id)
        payload = order_service.serialize_order(row, merchant=merchant, names=names)
        payload["merchant_name"] = merchant.business_name if merchant else ""
        items.append(payload)
    return AdminOrderPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/calls", response_model=AdminCallPage)
async def admin_calls(
    merchant_id: str = Query(default=""),
    direction: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CallLog)
    if merchant_id:
        stmt = stmt.where(CallLog.merchant_id == merchant_id)
    if direction:
        stmt = stmt.where(CallLog.direction == direction)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(await db.scalars(stmt.order_by(CallLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    merchants = await _merchants(db, {row.merchant_id for row in rows})
    order_ids = {row.order_id for row in rows if row.order_id}
    orders: dict[str, Order] = {}
    if order_ids:
        for order in await db.scalars(select(Order).where(Order.id.in_(order_ids))):
            orders[order.id] = order
    items = []
    for row in rows:
        payload = order_service.serialize_call_log(row)
        order = orders.get(row.order_id or "")
        merchant = merchants.get(row.merchant_id)
        payload.update(
            {
                "merchant_id": row.merchant_id,
                "merchant_name": merchant.business_name if merchant else "",
                "customer_name": order.customer_name if order else "",
                "order_ref": order.order_ref if order else "",
            }
        )
        items.append(payload)
    return AdminCallPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/recordings/{log_id}")
async def admin_recording(log_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.call_service import fetch_recording

    log = await db.get(CallLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Call log not found")
    content, media_type = await fetch_recording(log)
    return Response(content=content, media_type=media_type)


async def _merchants(db: AsyncSession, ids: set[str]) -> dict[str, Merchant]:
    if not ids:
        return {}
    return {row.id: row for row in await db.scalars(select(Merchant).where(Merchant.id.in_(ids)))}


# ------------------------------------------------------------------ sales inquiries
class SalesInquiryUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(new|contacted|demo|won|lost)$")
    admin_notes: str | None = Field(default=None, max_length=4000)


def _inquiry(row: SalesInquiry) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "email": row.email,
        "phone": row.phone,
        "company": row.company,
        "business_type": row.business_type,
        "country": row.country,
        "monthly_calls": row.monthly_calls,
        "message": row.message,
        "status": row.status,
        "admin_notes": row.admin_notes,
        "created_at": row.created_at,
    }


@router.get("/inquiries")
async def list_inquiries(
    status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SalesInquiry)
    if status:
        stmt = stmt.where(SalesInquiry.status == status)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await db.scalars(stmt.order_by(SalesInquiry.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [_inquiry(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/inquiries/{inquiry_id}")
async def update_inquiry(inquiry_id: str, data: SalesInquiryUpdate, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = await db.get(SalesInquiry, inquiry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    if data.status is not None:
        row.status = data.status
    if data.admin_notes is not None:
        row.admin_notes = data.admin_notes
    await db.commit()
    await db.refresh(row)
    return _inquiry(row)


@router.delete("/inquiries/{inquiry_id}", status_code=204)
async def delete_inquiry(inquiry_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = await db.get(SalesInquiry, inquiry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
