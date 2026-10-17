"""Owner dashboard: what the agent did for the business today / this week / this month."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import Merchant
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    range_key: str = Query(default="7d", alias="range", pattern="^(today|7d|30d)$"),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard.summary(db, merchant, range_key)
