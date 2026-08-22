"""Public endpoints (no auth): plans and platform info for the signup page.

Both reads are hot on the landing page and change rarely, so they are cached
(Redis or in-process) and invalidated by the admin write endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.db.session import get_db
from app.schemas.billing import PlanOut
from app import flows
from app.services import billing_service, voice_tiers

router = APIRouter(prefix="/api/public", tags=["public"])

PLANS_CACHE_KEY = "public:plans"
PLATFORM_CACHE_KEY = "public:platform"
CACHE_TTL = 300


@router.get("/plans", response_model=list[PlanOut])
async def public_plans(db: AsyncSession = Depends(get_db)):
    cached = await cache.get_json(PLANS_CACHE_KEY)
    if cached is not None:
        return cached
    plans = [
        PlanOut.model_validate(plan).model_dump() for plan in await billing_service.active_plans(db)
    ]
    await cache.set_json(PLANS_CACHE_KEY, plans, CACHE_TTL)
    return plans


@router.get("/platform")
async def public_platform(db: AsyncSession = Depends(get_db)):
    cached = await cache.get_json(PLATFORM_CACHE_KEY)
    if cached is not None:
        return cached
    settings_row = await billing_service.get_settings_row(db)
    payload = {
        "platform_name": settings_row.platform_name,
        "support_email": settings_row.support_email,
        "support_phone": settings_row.support_phone,
        "bkash_number": settings_row.bkash_number,
        "signup_enabled": settings_row.signup_enabled,
    }
    await cache.set_json(PLATFORM_CACHE_KEY, payload, CACHE_TTL)
    return payload


@router.get("/voice-tiers")
async def public_voice_tiers():
    """Voice ranks a merchant can choose — names, speakers and pricing only."""
    return voice_tiers.public_catalog()


@router.get("/service-types")
async def public_service_types():
    """The service verticals an account can run (ecommerce/courier)."""
    return flows.public_catalog()
