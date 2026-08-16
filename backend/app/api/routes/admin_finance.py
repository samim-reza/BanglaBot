"""Platform admin finance endpoints: monthly overview, cost-rate catalog."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import PlatformAdmin
from app.schemas.finance import RateOut, RateUpdate
from app.services import audit_service, finance_service

router = APIRouter(
    prefix="/api/admin/finance",
    tags=["admin-finance"],
    dependencies=[Depends(get_current_admin)],
)

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/overview")
async def overview(
    month: str | None = Query(None, description="YYYY-MM; default current month"),
    db: AsyncSession = Depends(get_db),
):
    if month and not _MONTH.match(month):
        raise HTTPException(400, "মাসের ফরম্যাট YYYY-MM হতে হবে")
    return await finance_service.finance_overview(db, month)


@router.get("/rates", response_model=list[RateOut])
async def list_rates(db: AsyncSession = Depends(get_db)):
    rates = await finance_service.current_rates(db)
    order = [seed["cost_key"] for seed in finance_service.RATE_SEEDS]
    return [rates[key] for key in order if key in rates]


@router.post("/rates", response_model=list[RateOut])
async def update_rate(
    body: RateUpdate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.cost_key not in finance_service.KNOWN_KEYS:
        raise HTTPException(404, "অজানা খরচের খাত")
    await finance_service.add_rate(
        db, cost_key=body.cost_key, rate_bdt=body.rate_bdt, created_by=admin.name
    )
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="rate_updated",
        detail=f"{admin.name} খরচের রেট বদলেছেন: {body.cost_key} → ৳{body.rate_bdt}",
    )
    await db.commit()
    rates = await finance_service.current_rates(db)
    order = [seed["cost_key"] for seed in finance_service.RATE_SEEDS]
    return [rates[key] for key in order if key in rates]
