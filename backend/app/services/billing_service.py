"""Plans, subscriptions, usage and invoices shared by merchant and admin routes."""

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallLog, Invoice, Merchant, Plan, PlatformSettings, Subscription
from app.models.base import new_id
from app.services import audit_service


def _aware(value: datetime | None) -> datetime | None:
    """Treat naive datetimes from the driver as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def get_settings_row(db: AsyncSession) -> PlatformSettings:
    row = await db.get(PlatformSettings, "default")
    if not row:
        row = PlatformSettings(id="default")
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def get_plan(db: AsyncSession, key: str) -> Plan | None:
    return (await db.execute(select(Plan).where(Plan.key == key))).scalar_one_or_none()


async def active_plans(db: AsyncSession) -> list[Plan]:
    rows = await db.execute(select(Plan).where(Plan.active).order_by(Plan.sort_order))
    return list(rows.scalars())


async def get_subscription(db: AsyncSession, merchant_id: str) -> Subscription | None:
    rows = await db.execute(
        select(Subscription)
        .where(Subscription.merchant_id == merchant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return rows.scalars().first()


async def start_trial(
    db: AsyncSession, merchant: Merchant, settings_row: PlatformSettings
) -> Subscription:
    """Create a trialing subscription for the merchant. db.add only — caller commits."""
    plan = await get_plan(db, settings_row.trial_plan_key)
    if not plan:
        plan = (
            (await db.execute(select(Plan).where(Plan.is_default_trial).limit(1))).scalars().first()
        )
    now = datetime.now(timezone.utc)
    # A trial must have a positive length even if the configured plan has none.
    trial_days = plan.trial_days if plan and plan.trial_days > 0 else 14
    sub = Subscription(
        merchant_id=merchant.id,
        plan_key=plan.key if plan else settings_row.trial_plan_key,
        status="trialing",
        current_period_start=now,
        current_period_end=now + timedelta(days=trial_days),
    )
    db.add(sub)
    return sub


async def usage_in_period(
    db: AsyncSession, merchant_id: str, start: datetime, end: datetime
) -> dict:
    # greatest() covers rows finished before the voice-tier system (billed_secs=0)
    # and any row whose completion webhook never priced it.
    calls, secs = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(func.greatest(CallLog.billed_secs, CallLog.duration_secs)), 0
                ),
            ).where(
                CallLog.merchant_id == merchant_id,
                CallLog.created_at >= start,
                CallLog.created_at < end,
            )
        )
    ).one()
    return {"calls_used": int(calls), "minutes_used": math.ceil(int(secs) / 60)}


async def generate_invoice(
    db: AsyncSession,
    merchant: Merchant,
    sub: Subscription,
    plan: Plan,
    period_start: datetime,
    period_end: datetime,
) -> Invoice | None:
    """Create a due invoice for the period. Skips zero-amount plans. db.add only."""
    if float(plan.price_monthly or 0) == 0:
        return None
    # Number derives from the invoice's own id — race-free under concurrency,
    # unlike a global COUNT(*) which collides on the unique constraint.
    invoice_id = new_id()
    invoice = Invoice(
        id=invoice_id,
        merchant_id=merchant.id,
        subscription_id=sub.id if sub else None,
        number=f"BB-{period_start:%Y%m}-{invoice_id[:6].upper()}",
        amount_due=plan.price_monthly,
        status="due",
        period_start=period_start,
        period_end=period_end,
        line_items=[
            {"label": f"{plan.name_bn} প্ল্যান — মাসিক ফি", "amount": float(plan.price_monthly)}
        ],
    )
    db.add(invoice)
    return invoice


async def maintain_subscription(
    db: AsyncSession, merchant: Merchant, sub: Subscription | None
) -> None:
    """Expire finished trials and roll finished active periods (commits when changed)."""
    if not sub or sub.status not in ("trialing", "active"):
        return
    now = datetime.now(timezone.utc)
    period_end = _aware(sub.current_period_end)
    if period_end is None or now <= period_end:
        return
    # Re-read under a row lock and re-check, so two concurrent requests cannot
    # both roll the same period and double-invoice it. (SQLite ignores the lock.)
    row = (
        await db.execute(
            select(Subscription)
            .where(Subscription.id == sub.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    period_end = _aware(row.current_period_end)
    if period_end is None or now <= period_end or row.status not in ("trialing", "active"):
        await db.commit()  # release the lock
        return
    if row.status == "trialing":
        row.status = "canceled"
        row.canceled_at = now
        await db.commit()
    else:
        new_start = period_end
        new_end = period_end + timedelta(days=30)
        row.current_period_start = new_start
        row.current_period_end = new_end
        plan = await get_plan(db, row.plan_key)
        already_billed = (
            (
                await db.execute(
                    select(Invoice.id)
                    .where(
                        Invoice.merchant_id == row.merchant_id,
                        Invoice.period_start == new_start,
                    )
                    .limit(1)
                )
            ).scalars().first()
            is not None
        )
        if plan and not already_billed:
            await generate_invoice(db, merchant, row, plan, new_start, new_end)
        await db.commit()


async def billing_summary(db: AsyncSession, merchant: Merchant) -> dict:
    settings_row = await get_settings_row(db)
    sub = await get_subscription(db, merchant.id)
    await maintain_subscription(db, merchant, sub)
    plan = await get_plan(db, sub.plan_key) if sub else None
    if sub:
        usage = await usage_in_period(
            db, merchant.id, sub.current_period_start, sub.current_period_end
        )
    else:
        usage = {"calls_used": 0, "minutes_used": 0}
    invoices_due = (
        await db.execute(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.merchant_id == merchant.id, Invoice.status == "due")
        )
    ).scalar_one()
    return {
        "plan": plan,
        "subscription": sub,
        "usage": {
            "calls_used": usage["calls_used"],
            "minutes_used": usage["minutes_used"],
            "call_limit": (plan.max_calls_per_month if plan else 0)
            + (sub.bonus_calls if sub else 0),
            "minute_limit": (plan.max_minutes_per_month if plan else 0)
            + (sub.bonus_minutes if sub else 0),
        },
        "invoices_due": int(invoices_due),
        "bkash_number": settings_row.bkash_number,
        "support_phone": settings_row.support_phone,
        "support_email": settings_row.support_email,
    }


async def change_plan(db: AsyncSession, merchant: Merchant, plan: Plan) -> Subscription:
    """Move the merchant to a paid plan. Commits.

    Mid-period switches on an active subscription keep the current period (so
    plan-hopping can never reset the usage window) and bill at the new price
    from the next rollover. All other cases start a fresh 30-day period with a
    due invoice (trial conversion / reactivation).
    """
    now = datetime.now(timezone.utc)
    sub = await get_subscription(db, merchant.id)
    period_end = _aware(sub.current_period_end) if sub else None
    if sub and sub.status == "active" and period_end and now < period_end:
        sub.plan_key = plan.key
    else:
        if not sub:
            sub = Subscription(merchant_id=merchant.id, plan_key=plan.key)
            db.add(sub)
        sub.plan_key = plan.key
        sub.status = "active"
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
        sub.canceled_at = None
        await db.flush()
        await generate_invoice(db, merchant, sub, plan, now, sub.current_period_end)
    audit_service.record(
        db,
        actor_role="merchant",
        actor_id=merchant.id,
        actor_name=merchant.business_name,
        action="plan_changed",
        detail=f"{merchant.business_name} নতুন প্ল্যানে গেছেন: {plan.name_bn}",
        merchant_id=merchant.id,
    )
    await db.commit()
    await db.refresh(sub)
    return sub


async def mrr(db: AsyncSession) -> float:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(Plan.price_monthly), 0))
            .select_from(Subscription)
            .join(Plan, Plan.key == Subscription.plan_key)
            .where(Subscription.status == "active")
        )
    ).scalar_one()
    return float(total)
