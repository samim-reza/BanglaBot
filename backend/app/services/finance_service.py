"""Financial engine: date-versioned cost rates, automatic per-call cost
attribution, and the monthly finance overview (revenue vs cost vs margin)."""

import math
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallCost, CallLog, CostRate, Invoice, Merchant, Plan, Subscription
from app.services import billing_service

# The catalog of platform cost components. Seeds come from COSTS.md (Twilio
# stack, ৳123/USD); every rate is editable in the admin finance page — edits
# append a new dated row, so old call costs keep their historical pricing.
RATE_SEEDS: list[dict] = [
    {"cost_key": "telephony", "label_bn": "টেলিফোনি (Twilio)", "unit": "per_minute", "rate_bdt": Decimal("7.9")},
    {"cost_key": "tts", "label_bn": "টিটিএস — ভয়েস (ElevenLabs)", "unit": "per_minute", "rate_bdt": Decimal("7.2")},
    {"cost_key": "llm", "label_bn": "এলএলএম (OpenAI)", "unit": "per_minute", "rate_bdt": Decimal("0.7")},
    {"cost_key": "stt", "label_bn": "এসটিটি — স্পিচ টু টেক্সট (OpenAI)", "unit": "per_minute", "rate_bdt": Decimal("0.2")},
    {"cost_key": "fixed_monthly", "label_bn": "নির্দিষ্ট মাসিক খরচ (সার্ভার/ডেটাবেস)", "unit": "per_month", "rate_bdt": Decimal("4600")},
]
KNOWN_KEYS = {seed["cost_key"] for seed in RATE_SEEDS}


async def current_rates(db: AsyncSession) -> dict[str, CostRate]:
    """Newest rate row per cost_key."""
    rows = await db.execute(select(CostRate).order_by(CostRate.effective_from))
    latest: dict[str, CostRate] = {}
    for row in rows.scalars():
        latest[row.cost_key] = row  # ascending order — last one wins
    return latest


def _rate(rates: dict[str, CostRate], key: str) -> Decimal:
    row = rates.get(key)
    return Decimal(row.rate_bdt) if row else Decimal(0)


async def compute_call_cost(db: AsyncSession, log: CallLog) -> CallCost | None:
    """Create the cost row for a finished call (idempotent, db.add only)."""
    if log.duration_secs <= 0:
        return None
    exists = (
        await db.execute(select(CallCost.id).where(CallCost.call_log_id == log.id).limit(1))
    ).scalars().first()
    if exists:
        return None
    rates = await current_rates(db)
    exact_minutes = Decimal(log.duration_secs) / Decimal(60)
    # Twilio bills whole minutes (a 70s call bills 2 min); AI usage is metered
    # on actual seconds.
    telephony_minutes = Decimal(math.ceil(log.duration_secs / 60))
    telephony = _rate(rates, "telephony") * telephony_minutes
    stt = _rate(rates, "stt") * exact_minutes
    tts = _rate(rates, "tts") * exact_minutes
    llm = _rate(rates, "llm") * exact_minutes
    cost = CallCost(
        call_log_id=log.id,
        merchant_id=log.merchant_id,
        duration_secs=log.duration_secs,
        billed_minutes=exact_minutes.quantize(Decimal("0.01")),
        telephony_bdt=telephony.quantize(Decimal("0.0001")),
        stt_bdt=stt.quantize(Decimal("0.0001")),
        tts_bdt=tts.quantize(Decimal("0.0001")),
        llm_bdt=llm.quantize(Decimal("0.0001")),
        total_bdt=(telephony + stt + tts + llm).quantize(Decimal("0.0001")),
        # Bucketed by the CALL's timestamp, not the insert time — backfilled
        # rows must land in the month the call actually happened.
        created_at=log.created_at,
    )
    try:
        # Savepoint: a concurrent duplicate insert (overlapping Twilio webhook
        # deliveries) must not poison the caller's transaction, which also
        # carries the call-status and order-state updates.
        async with db.begin_nested():
            db.add(cost)
            await db.flush()
    except IntegrityError:
        return None
    return cost


async def add_rate(
    db: AsyncSession, *, cost_key: str, rate_bdt: Decimal, created_by: str
) -> CostRate:
    """Append a new dated rate row (the old one stays for history). db.add only."""
    rates = await current_rates(db)
    prev = rates.get(cost_key)
    seed = next((s for s in RATE_SEEDS if s["cost_key"] == cost_key), None)
    row = CostRate(
        cost_key=cost_key,
        label_bn=prev.label_bn if prev else (seed["label_bn"] if seed else cost_key),
        unit=prev.unit if prev else (seed["unit"] if seed else "per_minute"),
        rate_bdt=rate_bdt,
        effective_from=datetime.now(timezone.utc),
        created_by=created_by,
    )
    db.add(row)
    return row


def _month_window(month: str | None) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if month:
        year_s, _, month_s = month.partition("-")
        year, mon = int(year_s), int(month_s)
    else:
        year, mon = now.year, now.month
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if mon == 12 else datetime(
        year, mon + 1, 1, tzinfo=timezone.utc
    )
    return start, end, f"{year:04d}-{mon:02d}"


async def finance_overview(db: AsyncSession, month: str | None) -> dict:
    start, end, month_key = _month_window(month)
    rates = await current_rates(db)

    telephony, stt, tts, llm, total, calls, minutes = (
        await db.execute(
            select(
                func.coalesce(func.sum(CallCost.telephony_bdt), 0),
                func.coalesce(func.sum(CallCost.stt_bdt), 0),
                func.coalesce(func.sum(CallCost.tts_bdt), 0),
                func.coalesce(func.sum(CallCost.llm_bdt), 0),
                func.coalesce(func.sum(CallCost.total_bdt), 0),
                func.count(),
                func.coalesce(func.sum(CallCost.billed_minutes), 0),
            ).where(CallCost.created_at >= start, CallCost.created_at < end)
        )
    ).one()
    fixed = _rate(rates, "fixed_monthly")
    call_cost_total = Decimal(total)
    total_cost = call_cost_total + fixed

    mrr = Decimal(str(await billing_service.mrr(db)))
    collected = Decimal(
        (
            await db.execute(
                select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
                    Invoice.status == "paid", Invoice.paid_at >= start, Invoice.paid_at < end
                )
            )
        ).scalar_one()
    )
    outstanding = Decimal(
        (
            await db.execute(
                select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
                    Invoice.status == "due"
                )
            )
        ).scalar_one()
    )

    # literal_column: repeating func.date_trunc("day", ...) renders 'day' as a
    # separate bind param per occurrence, and Postgres then rejects the GROUP BY
    # because it can't prove the SELECT and GROUP BY expressions are equal.
    bucket = func.date_trunc(literal_column("'day'"), CallCost.created_at)
    day_rows = await db.execute(
        select(
            bucket,
            func.coalesce(func.sum(CallCost.total_bdt), 0),
            func.count(),
        )
        .where(CallCost.created_at >= start, CallCost.created_at < end)
        .group_by(bucket)
        .order_by(bucket)
    )
    daily = [
        {"day": day.date().isoformat(), "cost_bdt": float(cost), "calls": int(count)}
        for day, cost, count in day_rows.all()
    ]

    merchant_rows = await db.execute(
        select(
            CallCost.merchant_id,
            Merchant.business_name,
            func.coalesce(func.sum(CallCost.total_bdt), 0),
            func.count(),
            func.coalesce(func.sum(CallCost.billed_minutes), 0),
        )
        .join(Merchant, Merchant.id == CallCost.merchant_id)
        .where(CallCost.created_at >= start, CallCost.created_at < end)
        .group_by(CallCost.merchant_id, Merchant.business_name)
        .order_by(func.sum(CallCost.total_bdt).desc())
        .limit(50)
    )
    merchant_costs = list(merchant_rows.all())
    merchant_ids = [row[0] for row in merchant_costs]
    revenue_by_merchant: dict[str, Decimal] = {}
    plan_by_merchant: dict[str, str] = {}
    if merchant_ids:
        sub_rows = await db.execute(
            select(Subscription.merchant_id, Subscription.status, Plan.name_bn, Plan.price_monthly)
            .join(Plan, Plan.key == Subscription.plan_key)
            .where(Subscription.merchant_id.in_(merchant_ids))
            .order_by(Subscription.created_at)
        )
        for merchant_id, status, plan_name, price in sub_rows.all():
            plan_by_merchant[merchant_id] = plan_name
            revenue_by_merchant[merchant_id] = (
                Decimal(price) if status == "active" else Decimal(0)
            )
    per_merchant = [
        {
            "merchant_id": merchant_id,
            "merchant_name": name,
            "plan_name_bn": plan_by_merchant.get(merchant_id, ""),
            "revenue_bdt": float(revenue_by_merchant.get(merchant_id, Decimal(0))),
            "cost_bdt": float(cost),
            "margin_bdt": float(revenue_by_merchant.get(merchant_id, Decimal(0)) - Decimal(cost)),
            "calls": int(count),
            "minutes": float(mins),
        }
        for merchant_id, name, cost, count, mins in merchant_costs
    ]

    # Margin compares the month's actual collections with the month's costs —
    # MRR is a point-in-time figure and would misstate historical months.
    gross = collected - total_cost
    per_minute_rate = sum(
        (_rate(rates, key) for key in ("telephony", "stt", "tts", "llm")), Decimal(0)
    )
    return {
        "month": month_key,
        "revenue": {
            "mrr": float(mrr),
            "collected": float(collected),
            "outstanding": float(outstanding),
        },
        "costs": {
            "telephony_bdt": float(telephony),
            "stt_bdt": float(stt),
            "tts_bdt": float(tts),
            "llm_bdt": float(llm),
            "call_total_bdt": float(call_cost_total),
            "fixed_bdt": float(fixed),
            "total_bdt": float(total_cost),
        },
        "calls": {
            "count": int(calls),
            "minutes": float(minutes),
            "avg_cost_bdt": float(call_cost_total / calls) if calls else 0.0,
        },
        "margin": {
            "gross_bdt": float(gross),
            "pct": float(gross / collected * 100) if collected > 0 else 0.0,
        },
        "unit": {"cost_per_minute_bdt": float(per_minute_rate)},
        "daily": daily,
        "per_merchant": per_merchant,
    }
