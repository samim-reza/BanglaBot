"""Order queries shared by merchant and admin routes."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallLog, Order, OrderStatus

# Merchants are Bangladeshi businesses — bucket daily insights in local time.
BD_TZ = ZoneInfo("Asia/Dhaka")

# Twilio final statuses meaning the customer never picked up.
UNANSWERED_STATUSES = ("no-answer", "busy", "failed", "canceled")


async def paginate_orders(
    db: AsyncSession,
    *,
    merchant_id: str | None = None,
    status: OrderStatus | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Order], int]:
    query = select(Order)
    if merchant_id:
        query = query.where(Order.merchant_id == merchant_id)
    if status:
        query = query.where(Order.status == status)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(
            Order.customer_name.ilike(like)
            | Order.customer_phone.ilike(like)
            | Order.order_ref.ilike(like)
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await db.execute(
        query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows.scalars()), total


async def get_call_logs(db: AsyncSession, order_id: str) -> list[CallLog]:
    rows = await db.execute(
        select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc())
    )
    return list(rows.scalars())


async def status_counts(db: AsyncSession, merchant_id: str | None = None) -> dict[str, int]:
    query = select(Order.status, func.count()).group_by(Order.status)
    if merchant_id:
        query = query.where(Order.merchant_id == merchant_id)
    rows = await db.execute(query)
    counts = {s.value: 0 for s in OrderStatus}
    for order_status, count in rows.all():
        counts[order_status.value] = count
    counts["total"] = sum(counts.values())
    return counts


async def call_insights(db: AsyncSession, merchant_id: str, days: int = 30) -> dict:
    """Per-day call outcomes plus headline totals for the merchant dashboard."""
    today_local = datetime.now(BD_TZ).date()
    first_day = today_local - timedelta(days=days - 1)
    # Window start = local midnight of the first bucketed day, in UTC.
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=BD_TZ)

    logs = (
        (
            await db.execute(
                select(CallLog).where(
                    CallLog.merchant_id == merchant_id, CallLog.created_at >= since
                )
            )
        )
        .scalars()
        .all()
    )

    day_keys = [(first_day + timedelta(days=i)).isoformat() for i in range(days)]
    daily = {
        key: {"day": key, "confirmed": 0, "cancelled": 0, "no_answer": 0, "other": 0}
        for key in day_keys
    }
    totals = {"calls": 0, "picked": 0, "confirmed": 0, "cancelled": 0, "no_answer": 0, "other": 0}
    total_talk_secs = 0

    for log in logs:
        created = log.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        key = created.astimezone(BD_TZ).date().isoformat()
        if log.outcome == "confirmed":
            bucket = "confirmed"
        elif log.outcome == "cancelled":
            bucket = "cancelled"
        elif log.call_status in UNANSWERED_STATUSES:
            bucket = "no_answer"
        else:
            # Picked up but no clear outcome (transfer/needs review), or still running.
            bucket = "other"
        totals["calls"] += 1
        totals[bucket] += 1
        if bucket in ("confirmed", "cancelled") or log.call_status == "completed":
            totals["picked"] += 1
            total_talk_secs += log.duration_secs
        if key in daily:
            daily[key][bucket] += 1

    picked = totals["picked"]
    totals["minutes"] = round(total_talk_secs / 60, 1)
    totals["avg_duration_secs"] = round(total_talk_secs / picked) if picked else 0
    totals["pickup_rate"] = round(picked * 100 / totals["calls"]) if totals["calls"] else 0
    totals["confirm_rate"] = round(totals["confirmed"] * 100 / picked) if picked else 0
    return {"days": days, "totals": totals, "daily": [daily[key] for key in day_keys]}
