"""Merchant-facing support tickets (all scoped to the logged-in merchant)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import Merchant, SupportMessage, SupportTicket
from app.schemas.common import Page
from app.schemas.support import (
    MessageOut,
    TicketCreate,
    TicketDetail,
    TicketOut,
    TicketReply,
)
from app.services import audit_service

router = APIRouter(prefix="/api/support", tags=["support"])


async def _own_ticket(db: AsyncSession, merchant: Merchant, ticket_id: str) -> SupportTicket:
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket or ticket.merchant_id != merchant.id:
        raise HTTPException(404, "টিকিট পাওয়া যায়নি")
    return ticket


async def _ticket_detail(db: AsyncSession, ticket: SupportTicket) -> TicketDetail:
    rows = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.created_at.asc())
    )
    detail = TicketDetail.model_validate(ticket)
    detail.messages = [MessageOut.model_validate(m) for m in rows.scalars()]
    return detail


@router.get("/tickets", response_model=Page[TicketOut])
async def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.merchant_id == merchant.id)
        )
    ).scalar_one()
    rows = await db.execute(
        select(SupportTicket)
        .where(SupportTicket.merchant_id == merchant.id)
        .order_by(SupportTicket.last_message_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=list(rows.scalars()), total=total, page=page, page_size=page_size)


@router.post("/tickets", response_model=TicketDetail, status_code=201)
async def create_ticket(
    body: TicketCreate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    ticket = SupportTicket(
        merchant_id=merchant.id,
        subject=body.subject,
        priority=body.priority if body.priority in ("normal", "urgent") else "normal",
        last_message_at=now,
    )
    db.add(ticket)
    await db.flush()
    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            author_role="merchant",
            author_name=merchant.business_name,
            body=body.message,
        )
    )
    audit_service.record(
        db,
        actor_role="merchant",
        actor_id=merchant.id,
        actor_name=merchant.business_name,
        action="ticket_opened",
        detail=f"{merchant.business_name} নতুন টিকিট খুলেছেন: {body.subject}",
        merchant_id=merchant.id,
    )
    await db.commit()
    await db.refresh(ticket)
    return await _ticket_detail(db, ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _own_ticket(db, merchant, ticket_id)
    return await _ticket_detail(db, ticket)


@router.post("/tickets/{ticket_id}/messages", response_model=TicketDetail)
async def reply_ticket(
    ticket_id: str,
    body: TicketReply,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _own_ticket(db, merchant, ticket_id)
    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            author_role="merchant",
            author_name=merchant.business_name,
            body=body.body,
        )
    )
    ticket.status = "open"
    ticket.last_message_at = datetime.now(timezone.utc)
    audit_service.record(
        db,
        actor_role="merchant",
        actor_id=merchant.id,
        actor_name=merchant.business_name,
        action="ticket_replied",
        detail=f"{merchant.business_name} টিকিটে উত্তর দিয়েছেন: {ticket.reference}",
        merchant_id=merchant.id,
    )
    await db.commit()
    await db.refresh(ticket)
    return await _ticket_detail(db, ticket)
