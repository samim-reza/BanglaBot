"""Admin: the tier + add-on catalog editor, signup settings, offered verticals,
subscriptions, and approving / rejecting self-serve signups."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.core.addons import CATEGORIES, GRANT_KEYS, PERIODS
from app.core.plans import ALL_CHANNELS, ALL_FEATURES, CAPABILITY_FEATURES, CHANNEL_LABELS, FLOW_EDITING_LEVELS, PRODUCTS
from app.core.security import ROLE_FINANCE, ROLE_SUPERADMIN, ROLE_SUPPORT
from app.db.session import get_db
from app.models import Merchant, Subscription
from app.schemas.plans import CatalogIn, SignupSettingsIn, VerticalsIn
from app.schemas.signup import SignupDecisionIn
from app.services import audit_service, catalog_plans, signup_queries, signup_service, subscription_service

router = APIRouter(prefix="/api/admin", tags=["admin-plans"])

SUPERADMIN = require_admin(ROLE_SUPERADMIN)
OPERATORS = require_admin(ROLE_SUPERADMIN, ROLE_SUPPORT)
BILLING = require_admin(ROLE_SUPERADMIN, ROLE_FINANCE, ROLE_SUPPORT)


def _editor() -> dict:
    return {
        **catalog_plans.snapshot(),
        "defaults": catalog_plans.defaults(),
        "options": {
            "channels": [{"key": key, "label": CHANNEL_LABELS.get(key, key)} for key in ALL_CHANNELS],
            "features": list(ALL_FEATURES),
            "capabilities": list(CAPABILITY_FEATURES),
            "grants": list(GRANT_KEYS),
            "categories": list(CATEGORIES),
            "periods": list(PERIODS),
            "products": list(PRODUCTS),
            "flow_editing": list(FLOW_EDITING_LEVELS),
            "verticals": catalog_plans.all_vertical_keys(),
        },
    }


# ------------------------------------------------------------------ catalog
@router.get("/plans/catalog")
async def get_catalog(_: AdminPrincipal = Depends(require_admin)):
    await catalog_plans.ensure_fresh()
    return _editor()


@router.put("/plans/catalog")
async def put_catalog(data: CatalogIn, request: Request, admin: AdminPrincipal = Depends(SUPERADMIN), db: AsyncSession = Depends(get_db)):
    """The complete catalog (every tier and add-on); keys in use can be hidden, not removed."""
    await catalog_plans.load(db)
    result = await catalog_plans.save_catalog(db, data, by=admin.id)
    audit_service.stage(
        db, action="catalog.updated", **admin.audit_actor, target_type="catalog", target_id="plans", request=request,
        meta={"tiers": [tier.key for tier in data.tiers], "addons": [addon.key for addon in data.addons], **result["removed"]},
    )
    await db.commit()
    return _editor()


@router.get("/plans/settings")
async def get_signup_settings(_: AdminPrincipal = Depends(require_admin)):
    await catalog_plans.ensure_fresh()
    return catalog_plans.signup_settings()


@router.put("/plans/settings")
async def put_signup_settings(
    data: SignupSettingsIn, request: Request, admin: AdminPrincipal = Depends(SUPERADMIN), db: AsyncSession = Depends(get_db)
):
    settings = await catalog_plans.save_signup_settings(db, data, by=admin.id)
    audit_service.stage(db, action="signup.settings_updated", **admin.audit_actor, target_type="settings", target_id="signup",
                        request=request, meta=settings)
    await db.commit()
    return settings


# ------------------------------------------------------------------ verticals
def _verticals() -> list[dict]:
    from app.verticals import VERTICALS

    offered = set(catalog_plans.offered_verticals())
    return [{"key": key, "label": v.label, "description": v.description, "offered": key in offered} for key, v in VERTICALS.items()]


@router.get("/verticals")
async def get_verticals(_: AdminPrincipal = Depends(require_admin)):
    await catalog_plans.ensure_fresh()
    return {"items": _verticals()}


@router.put("/verticals")
async def put_verticals(data: VerticalsIn, request: Request, admin: AdminPrincipal = Depends(SUPERADMIN), db: AsyncSession = Depends(get_db)):
    """Which verticals new accounts may pick at signup."""
    await catalog_plans.save_offered_verticals(db, data.offered, by=admin.id)
    audit_service.stage(db, action="verticals.updated", **admin.audit_actor, target_type="settings", target_id="verticals",
                        request=request, meta={"offered": data.offered})
    await db.commit()
    return {"items": _verticals()}


# ------------------------------------------------------------------ subscriptions + signups
@router.get("/subscriptions")
async def list_subscriptions(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str = Query(default="", max_length=200),
    status: str = Query(default="", pattern="^(|pending|active|past_due|cancelled)$"),
    merchant_id: str = Query(default="", max_length=64),
    tier: str = Query(default="", max_length=24),
    kind: str = Query(default="", pattern="^(|signup|change|renewal|manual)$"),
    _: AdminPrincipal = Depends(BILLING),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await subscription_service.list_subscriptions(
            db, limit=limit, cursor=cursor, status=status, merchant_id=merchant_id, tier=tier, kind=kind
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


@router.get("/signups")
async def list_signups(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str = Query(default="", max_length=200),
    status: str = Query(default="", pattern="^(|pending_payment|awaiting_approval|approved|rejected)$"),
    _: AdminPrincipal = Depends(OPERATORS),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await signup_queries.list_signups(db, limit=limit, cursor=cursor, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


@router.post("/signups/{merchant_id}/{decision}")
async def decide_signup(
    merchant_id: str,
    decision: str,
    data: SignupDecisionIn,
    request: Request,
    admin: AdminPrincipal = Depends(OPERATORS),
    db: AsyncSession = Depends(get_db),
):
    """``approve`` (activates the account; ``mark_paid`` = paid offline) or ``reject``."""
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=404, detail="Unknown action")
    record = await signup_queries.by_merchant(db, merchant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Signup not found")
    if decision == "approve":
        await signup_service.approve(db, record, by=admin.id, note=data.note, mark_paid=data.mark_paid)
    else:
        await signup_service.reject(db, record, by=admin.id, note=data.note)
    audit_service.stage(
        db, action="signup.approved" if decision == "approve" else "signup.rejected", **admin.audit_actor,
        target_type="merchant", target_id=merchant_id, merchant_id=merchant_id, request=request,
        meta={"mark_paid": data.mark_paid} if decision == "approve" else {},
    )
    await db.commit()
    merchant = await db.get(Merchant, merchant_id)
    sub = await db.get(Subscription, record.subscription_id) if record.subscription_id else None
    return signup_queries.serialize(record, merchant, sub)
