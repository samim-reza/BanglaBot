"""Records (orders / appointments / leads / bookings): CRUD, listing, stats, JSON.

Input is validated against the account's vertical field specs (the same specs
that render the portal form); vertical-specific fields live in ``details``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.regions import region_of
from app.flows.timefmt import business_tz
from app.models import CallLog, CatalogItem, Merchant, Order, OrderStatus
from app.schemas.order import OrderCreate, OrderUpdate
from app.verticals import vertical_for
from app.verticals.forms import FieldError, split_record


#: Record text columns that are NOT NULL (a cleared value is stored as "").
TEXT_COLUMNS = frozenset({"order_ref", "address", "items_summary", "notes"})


def serialize_call_log(log: CallLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "order_id": log.order_id,
        "direction": log.direction or "outbound",
        "flow": log.flow or "",
        "caller_number": log.caller_number or "",
        "twilio_call_sid": log.twilio_call_sid or "",
        "recording_sid": log.recording_sid or "",
        "call_status": log.call_status or "",
        "outcome": log.outcome or "",
        "transcript": log.transcript or "",
        "language": log.language or "",
        "duration_secs": int(log.duration_secs or 0),
        "final_node": log.final_node or "",
        "llm_prompt_tokens": int(log.llm_prompt_tokens or 0),
        "llm_cached_tokens": int(getattr(log, "llm_cached_tokens", 0) or 0),
        "llm_completion_tokens": int(log.llm_completion_tokens or 0),
        "tts_chars": int(log.tts_chars or 0),
        "tts_cache_hits": int(log.tts_cache_hits or 0),
        "created_at": log.created_at,
    }


def serialize_order(order: Order, *, merchant: Merchant | None = None, names: dict[str, str] | None = None) -> dict[str, Any]:
    status = order.status.value if isinstance(order.status, OrderStatus) else str(order.status or "")
    amount = order.total_amount if order.total_amount is not None else Decimal("0")
    names = names or {}
    summary = ""
    if merchant is not None:
        vertical = vertical_for(merchant)
        if vertical.summarize is not None:
            try:
                summary = vertical.summarize(order, names)
            except Exception:  # noqa: BLE001 — a summary is cosmetic
                summary = ""
    return {
        "id": order.id,
        "merchant_id": order.merchant_id,
        "kind": order.kind or "order",
        "source": order.source or "manual",
        "order_ref": order.order_ref or "",
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "address": order.address or "",
        "items_summary": order.items_summary or "",
        "total_amount": f"{Decimal(str(amount)):.2f}",
        "currency": order.currency or (merchant.currency if merchant is not None else ""),
        "status": status,
        "notes": order.notes or "",
        "catalog_item_id": order.catalog_item_id,
        "catalog_item_name": names.get(str(order.catalog_item_id or ""), ""),
        "scheduled_at": order.scheduled_at,
        "details": dict(order.details or {}),
        "summary": summary,
        "flow_data": dict(order.flow_data or {}),
        "call_attempts": int(order.call_attempts or 0),
        "last_call_at": order.last_call_at,
        "created_at": order.created_at,
    }


async def catalog_names(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    ids = {item for item in ids if item}
    if not ids:
        return {}
    rows = await db.execute(select(CatalogItem.id, CatalogItem.name).where(CatalogItem.id.in_(ids)))
    return {item_id: name for item_id, name in rows}


async def serialize_many(db: AsyncSession, rows: list[Order], merchant: Merchant | None) -> list[dict[str, Any]]:
    names = await catalog_names(db, {str(row.catalog_item_id or "") for row in rows})
    return [serialize_order(row, merchant=merchant, names=names) for row in rows]


def parse_status(value: str | None) -> OrderStatus | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return OrderStatus(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status '{value}'") from exc


def _apply_filters(stmt: Select, *, status: OrderStatus | None, search: str, kind: str = "", upcoming: bool = False) -> Select:
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if kind:
        stmt = stmt.where(Order.kind == kind)
    if upcoming:
        stmt = stmt.where(Order.scheduled_at >= utcnow())
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
    kind: str = "",
    upcoming: bool = False,
    sort: str = "created",
) -> tuple[list[Order], int]:
    stmt = select(Order)
    if merchant_id:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    stmt = _apply_filters(stmt, status=status, search=search, kind=kind, upcoming=upcoming)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    if sort == "scheduled":
        order_by = (Order.scheduled_at.asc().nulls_last(), Order.created_at.desc())
    else:
        order_by = (Order.created_at.desc(),)
    rows = await db.scalars(stmt.order_by(*order_by).offset((page - 1) * page_size).limit(page_size))
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
        raise HTTPException(status_code=404, detail="Record not found")
    return order


async def order_call_logs(db: AsyncSession, order_id: str) -> list[CallLog]:
    rows = await db.scalars(select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc()))
    return list(rows)


def _tz(merchant: Merchant):
    return business_tz(merchant.timezone or region_of(merchant).timezone)


async def _check_catalog(db: AsyncSession, merchant: Merchant, item_id: str | None) -> None:
    if not item_id:
        return
    item = await db.get(CatalogItem, item_id)
    if item is None or item.merchant_id != merchant.id:
        raise HTTPException(status_code=422, detail="catalog_item_id does not belong to this account")


def _split(merchant: Merchant, payload: dict[str, Any], *, partial: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return split_record(vertical_for(merchant), payload, partial=partial, tz=_tz(merchant))
    except FieldError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def create_order(db: AsyncSession, merchant: Merchant, data: OrderCreate) -> Order:
    payload = data.model_dump()
    payload.update(data.model_extra or {})
    columns, details = _split(merchant, payload, partial=False)
    await _check_catalog(db, merchant, columns.get("catalog_item_id"))
    vertical = vertical_for(merchant)
    scheduled = columns.get("scheduled_at")
    order = Order(
        merchant_id=merchant.id,
        kind=vertical.record_kind,
        source="manual",
        order_ref=str(columns.get("order_ref") or data.order_ref or "").strip(),
        customer_name=str(columns.get("customer_name") or data.customer_name),
        customer_phone=str(columns.get("customer_phone") or data.customer_phone).strip(),
        address=str(columns.get("address") or data.address or "").strip(),
        items_summary=str(columns.get("items_summary") or data.items_summary or "").strip(),
        total_amount=Decimal(str(columns.get("total_amount") or data.total_amount or 0)).quantize(Decimal("0.01")),
        currency=merchant.currency or region_of(merchant).currency,
        notes=str(columns.get("notes") or data.notes or "").strip(),
        catalog_item_id=columns.get("catalog_item_id") or None,
        scheduled_at=scheduled if isinstance(scheduled, datetime) else None,
        details={key: value for key, value in details.items() if value is not None},
        status=OrderStatus.pending,
    )
    if not order.items_summary and order.catalog_item_id:
        names = await catalog_names(db, {order.catalog_item_id})
        order.items_summary = names.get(order.catalog_item_id, "")
    db.add(order)
    await db.commit()
    await db.refresh(order)
    from app.services import notification_service

    notification_service.after_record_change(order.id)
    return order


async def update_order(db: AsyncSession, merchant: Merchant, order: Order, data: OrderUpdate) -> Order:
    if order.status == OrderStatus.calling and data.status is not None:
        raise HTTPException(status_code=409, detail="A call is in progress for this record")
    payload = data.model_dump(exclude_unset=True)
    payload.update(data.model_extra or {})
    status = payload.pop("status", None)
    columns, details = _split(merchant, payload, partial=True)
    if "catalog_item_id" in columns:
        await _check_catalog(db, merchant, columns.get("catalog_item_id"))
    for key, value in columns.items():
        if key == "total_amount":
            value = Decimal(str(value or 0)).quantize(Decimal("0.01"))
        elif isinstance(value, str):
            value = value.strip()
        if value is None:
            if key in ("customer_name", "customer_phone"):
                continue
            if key in TEXT_COLUMNS:
                # A cleared field: these columns are NOT NULL, so empty means "".
                value = ""
        setattr(order, key, value)
    if details:
        merged = dict(order.details or {})
        merged.update(details)
        order.details = {key: value for key, value in merged.items() if value is not None}
    if status is not None:
        order.status = OrderStatus(status)
    order.updated_at = utcnow()
    await db.commit()
    await db.refresh(order)
    from app.services import notification_service

    notification_service.after_record_change(order.id)
    return order


async def delete_order(db: AsyncSession, order: Order) -> None:
    if order.status == OrderStatus.calling:
        raise HTTPException(status_code=409, detail="A call is in progress for this record")
    # Detach call logs (usage history survives the record).
    details = dict(order.details or {})
    merchant = await db.get(Merchant, order.merchant_id)
    await db.execute(update(CallLog).where(CallLog.order_id == order.id).values(order_id=None))
    await db.delete(order)
    await db.commit()
    if merchant is not None:
        from app.services import notification_service

        notification_service.after_record_delete(merchant, details)
