"""The admin console's finance API (finance + superadmin roles): cost, revenue, margin,
breakdowns, per-account economics, per-call cost lines, the price book, spend caps,
forecast and CSV export. ``month`` is ``YYYY-MM`` (UTC); empty = this month."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.core.security import ROLE_FINANCE, ROLE_SUPERADMIN
from app.db.session import get_db
from app.finance import accounts, export, guard, pricebook, reports
from app.finance.periods import Month, parse_month
from app.schemas.finance import (
    AccountFinancePage,
    CallCosts,
    CapsOut,
    CapsPut,
    FinanceBreakdown,
    FinanceForecast,
    FinanceOverview,
    PricebookOut,
    PricebookPut,
)
from app.services import audit_service

router = APIRouter(prefix="/api/admin/finance", tags=["admin-finance"])

finance_admin = require_admin(ROLE_SUPERADMIN, ROLE_FINANCE)
MONTH = Query(default="", max_length=7, description="YYYY-MM (UTC); empty = this month")


def _month(value: str) -> Month:
    try:
        return parse_month(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/overview", response_model=FinanceOverview)
async def overview(month: str = MONTH, _: AdminPrincipal = Depends(finance_admin), db: AsyncSession = Depends(get_db)):
    return await reports.overview(db, _month(month))


@router.get("/breakdown", response_model=FinanceBreakdown)
async def breakdown(
    by: str = Query(default="category", pattern="^(category|provider|model|vertical|account)$"),
    month: str = MONTH,
    limit: int = Query(default=50, ge=1, le=100),
    _: AdminPrincipal = Depends(finance_admin),
    db: AsyncSession = Depends(get_db),
):
    return await reports.breakdown(db, _month(month), by, limit=limit)


@router.get("/accounts", response_model=AccountFinancePage)
async def account_list(
    month: str = MONTH,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str = Query(default="", max_length=200),
    _: AdminPrincipal = Depends(finance_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await accounts.list_accounts(db, _month(month), limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


@router.get("/calls/{call_log_id}/costs", response_model=CallCosts)
async def call_costs(call_log_id: str, _: AdminPrincipal = Depends(finance_admin), db: AsyncSession = Depends(get_db)):
    found = await reports.call_costs(db, call_log_id[:64])
    if found is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return found


@router.get("/forecast", response_model=FinanceForecast)
async def forecast(month: str = MONTH, _: AdminPrincipal = Depends(finance_admin), db: AsyncSession = Depends(get_db)):
    return await reports.forecast(db, _month(month))


# ------------------------------------------------------------------ price book
async def _pricebook_out(db: AsyncSession, at: date) -> PricebookOut:
    versions = await pricebook.load_versions(db)
    book = pricebook.build(versions, at)
    return PricebookOut(at=at.isoformat(), **book.as_json(), versions=versions)


@router.get("/pricebook", response_model=PricebookOut)
async def get_pricebook(
    at: date | None = Query(default=None, description="The book in force on this day (default: today, UTC)"),
    _: AdminPrincipal = Depends(finance_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _pricebook_out(db, at or datetime.now(timezone.utc).date())


@router.put("/pricebook", response_model=PricebookOut)
async def put_pricebook(data: PricebookPut, request: Request, admin: AdminPrincipal = Depends(finance_admin), db: AsyncSession = Depends(get_db)):
    effective = data.effective_from or datetime.now(timezone.utc).date()
    entries = [entry.model_dump(exclude_none=True) for entry in data.prices]
    try:
        version = await pricebook.add_version(db, effective_from=effective, entries=entries, note=data.note, updated_by=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_service.stage(
        db, action="finance.pricebook_changed", **admin.audit_actor, target_type="pricebook", target_id=effective.isoformat(),
        request=request, meta={"effective_from": effective.isoformat(), "keys": sorted(version["prices"])[:40], "note": data.note[:200]},
    )
    await db.commit()
    return await _pricebook_out(db, effective)


# ------------------------------------------------------------------ cost guard
@router.get("/caps", response_model=CapsOut)
async def get_caps(_: AdminPrincipal = Depends(finance_admin), db: AsyncSession = Depends(get_db)):
    await guard.refresh(db)
    return CapsOut(items=guard.status())


@router.put("/caps", response_model=CapsOut)
async def put_caps(data: CapsPut, request: Request, admin: AdminPrincipal = Depends(finance_admin), db: AsyncSession = Depends(get_db)):
    caps = await guard.set_caps(db, dict(data.caps), updated_by=admin.id)
    audit_service.stage(
        db, action="finance.caps_changed", **admin.audit_actor, target_type="caps", request=request,
        meta={"caps": {key: (None if value is None else str(value)) for key, value in caps.items()}},
    )
    await db.commit()
    return CapsOut(items=guard.status())


# ------------------------------------------------------------------ export
@router.get("/export.csv")
async def export_csv(
    month: str = MONTH,
    kind: str = Query(default="daily", pattern="^(daily|accounts)$"),
    _: AdminPrincipal = Depends(finance_admin),
):
    period = _month(month)
    filename = f"banglabot-finance-{kind}-{period.key}.csv"
    return StreamingResponse(
        export.stream_own_session(period, kind),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )
