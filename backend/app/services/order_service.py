"""Order CRUD, listing, stats and JSON serialization (merchant-scoped)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.models import CallLog, Merchant, Order, OrderStatus
from app.schemas.order import OrderCreate, OrderUpdate


def serialize_call_log(log: CallLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "order_id": log.order_id,
        "twilio_call_sid": log.twilio_call_sid or "",
        "recording_sid": log.recording_sid or "",
        "call_status": log.call_status or "",
        "outcome": log.outcome or "",
        "transcript": log.transcript or "",
        "language": log.language or "",
        "duration_secs": int(log.duration_secs or 0),
        "final_node": log.final_node or "",
        "created_at": log.created_at,
    }


def serialize_order(order: Order) -> dict[str, Any]:
    status = order.status.value if isinstance(order.status, OrderStatus) else str(order.status or "")
    amount = order.total_amount if order.total_amount is not None else Decimal("0")
    return {
        "id": order.id,
        "merchant_id": order.merchant_id,
        "order_ref": order.order_ref or "",
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "address": order.address or "",
        "items_summary": order.items_summary or "",
        "total_amount": f"{Decimal(str(amount)):.2f}",
        "currency": order.currency or "BDT",
        "status": status,
        "notes": order.notes or "",
        "flow_data": dict(order.flow_data or {}),
        "call_attempts": int(order.call_attempts or 0),
        "last_call_at": order.last_call_at,
        "created_at": order.created_at,
    }


def parse_status(value: str | None) -> OrderStatus | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return OrderStatus(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status '{value}'") from exc


def _apply_filters(stmt: Select, *, status: OrderStatus | None, search: str) -> Select:
    if status is not None:
        stmt = stmt.where(Order.status == status)
    term = " ".join(str(search or "").split())
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                Order.customer_name.ilike(like),
                Order.customer_phone.ilike(like),
                Order.order_ref.ilike(like),
                Order.items_summary.ilike(like),
            )
        )
    return stmt


async def list_orders(
    db: AsyncSession,
    *,
    merchant_id: str | None,
    status: OrderStatus | None,
    search: str,
    page: int,
    page_size: int,
) -> tuple[list[Order], int]:
    stmt = select(Order)
    if merchant_id:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    stmt = _apply_filters(stmt, status=status, search=search)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await db.scalars(stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


async def order_stats(db: AsyncSession, merchant_id: str) -> dict[str, int]:
    rows = await db.execute(
        select(Order.status, func.count()).where(Order.merchant_id == merchant_id).group_by(Order.status)
    )
    stats = {status.value: 0 for status in OrderStatus}
    total = 0
    for status, count in rows:
        key = status.value if isinstance(status, OrderStatus) else str(status)
        stats[key] = int(count)
        total += int(count)
    stats["total"] = total
    return stats


async def get_order(db: AsyncSession, merchant: Merchant, order_id: str) -> Order:
    order = await db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def order_call_logs(db: AsyncSession, order_id: str) -> list[CallLog]:
    rows = await db.scalars(select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc()))
    return list(rows)


async def create_order(db: AsyncSession, merchant: Merchant, data: OrderCreate) -> Order:
    order = Order(
        merchant_id=merchant.id,
        order_ref=data.order_ref.strip(),
        customer_name=data.customer_name,
        customer_phone=data.customer_phone.strip(),
        address=data.address.strip(),
        items_summary=data.items_summary.strip(),
        total_amount=Decimal(str(data.total_amount)).quantize(Decimal("0.01")),
        currency="BDT",
        notes=data.notes.strip(),
        status=OrderStatus.pending,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def update_order(db: AsyncSession, order: Order, data: OrderUpdate) -> Order:
    if order.status == OrderStatus.calling and data.status is not None:
        raise HTTPException(status_code=409, detail="A call is in progress for this order")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None:
            continue
        if key == "total_amount":
            value = Decimal(str(value)).quantize(Decimal("0.01"))
        elif isinstance(value, str) and key != "status":
            value = value.strip()
        setattr(order, key, value)
    order.updated_at = utcnow()
    await db.commit()
    await db.refresh(order)
    return order


async def delete_order(db: AsyncSession, order: Order) -> None:
    if order.status == OrderStatus.calling:
        raise HTTPException(status_code=409, detail="A call is in progress for this order")
    # Detach call logs (usage history survives the order).
    await db.execute(update(CallLog).where(CallLog.order_id == order.id).values(order_id=None))
    await db.delete(order)
    await db.commit()
