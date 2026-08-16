"""Platform admin support endpoints: the ticket queue across all merchants."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import Merchant, PlatformAdmin, SupportMessage, SupportTicket
from app.schemas.common import Page
from app.schemas.support import (
    AdminTicketDetail,
    AdminTicketOut,
    MessageOut,
    TicketOut,
    TicketPatch,
    TicketReply,
)
from app.services import audit_service

router = APIRouter(
    prefix="/api/admin/support",
    tags=["admin-support"],
    dependencies=[Depends(get_current_admin)],
)


async def _ticket_or_404(db: AsyncSession, ticket_id: str) -> SupportTicket:
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "টিকিট পাওয়া যায়নি")
    return ticket


async def _admin_detail(db: AsyncSession, ticket: SupportTicket) -> AdminTicketDetail:
    merchant = await db.get(Merchant, ticket.merchant_id)
    rows = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.created_at.asc())
    )
    return AdminTicketDetail(
        **TicketOut.model_validate(ticket).model_dump(),
        merchant_name=merchant.business_name if merchant else "",
        messages=[MessageOut.model_validate(m) for m in rows.scalars()],
    )


@router.get("/tickets", response_model=Page[AdminTicketOut])
async def list_tickets(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(SupportTicket, Merchant.business_name).join(
        Merchant, Merchant.id == SupportTicket.merchant_id
    )
    if status:
        query = query.where(SupportTicket.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await db.execute(
        query.order_by(SupportTicket.last_message_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        AdminTicketOut(**TicketOut.model_validate(ticket).model_dump(), merchant_name=name)
        for ticket, name in rows.all()
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetail)
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    ticket = await _ticket_or_404(db, ticket_id)
    return await _admin_detail(db, ticket)


@router.post("/tickets/{ticket_id}/messages", response_model=AdminTicketDetail)
async def reply_ticket(
    ticket_id: str,
    body: TicketReply,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _ticket_or_404(db, ticket_id)
    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            author_role="admin",
            author_name=admin.name,
            body=body.body,
        )
    )
    ticket.status = "answered"
    ticket.last_message_at = datetime.now(timezone.utc)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="ticket_replied",
        detail=f"{admin.name} টিকিটে উত্তর দিয়েছেন: {ticket.reference}",
        merchant_id=ticket.merchant_id,
    )
    await db.commit()
    await db.refresh(ticket)
    return await _admin_detail(db, ticket)


@router.patch("/tickets/{ticket_id}", response_model=AdminTicketDetail)
async def update_ticket(
    ticket_id: str,
    body: TicketPatch,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _ticket_or_404(db, ticket_id)
    changes = []
    if body.status is not None:
        if body.status not in ("open", "answered", "closed"):
            raise HTTPException(400, "অবৈধ স্ট্যাটাস")
        ticket.status = body.status
        changes.append(f"স্ট্যাটাস: {body.status}")
    if body.priority is not None:
        if body.priority not in ("normal", "urgent"):
            raise HTTPException(400, "অবৈধ অগ্রাধিকার")
        ticket.priority = body.priority
        changes.append(f"অগ্রাধিকার: {body.priority}")
    if changes:
        audit_service.record(
            db,
            actor_role="admin",
            actor_id=admin.id,
            actor_name=admin.name,
            action="ticket_status",
            detail=f"টিকিট {ticket.reference} আপডেট — " + ", ".join(changes),
            merchant_id=ticket.merchant_id,
        )
    await db.commit()
    await db.refresh(ticket)
    return await _admin_detail(db, ticket)
