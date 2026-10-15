"""Sales inquiries from the website's contact form: list, update, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import SalesInquiry

router = APIRouter()


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
