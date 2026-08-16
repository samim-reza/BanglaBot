"""Subscription enforcement gate for outbound confirmation calls."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Merchant
from app.services import audit_service, billing_service

UPGRADE_HINT = "বিলিং পেজ থেকে প্ল্যান আপগ্রেড করুন"

MESSAGES = {
    "no_subscription": "কোনো সাবস্ক্রিপশন নেই — বিলিং পেজ থেকে একটি প্ল্যান নিন",
    "trial_expired": "ফ্রি ট্রায়াল শেষ — চালিয়ে যেতে একটি প্ল্যান নিন",
    "subscription_inactive": "সাবস্ক্রিপশন সক্রিয় নেই — বিলিং পেজ দেখুন",
    "call_limit": "এই মাসের কল সীমা শেষ — প্ল্যান আপগ্রেড করুন",
    "minute_limit": "এই মাসের মিনিট সীমা শেষ — প্ল্যান আপগ্রেড করুন",
}


async def check_can_call(db: AsyncSession, merchant: Merchant) -> None:
    """Raise HTTPException(402) when the merchant may not start a call."""
    settings_row = await billing_service.get_settings_row(db)
    sub = await billing_service.get_subscription(db, merchant.id)
    await billing_service.maintain_subscription(db, merchant, sub)

    reason = None
    if not sub:
        reason = "no_subscription"
    elif sub.status not in ("trialing", "active"):
        # Durable discriminator: a canceled sub still on a trial plan means the
        # trial lapsed — keep showing the conversion message on every retry.
        plan = await billing_service.get_plan(db, sub.plan_key)
        trial_lapsed = sub.status == "canceled" and plan is not None and plan.trial_days > 0
        reason = "trial_expired" if trial_lapsed else "subscription_inactive"
    else:
        plan = await billing_service.get_plan(db, sub.plan_key)
        if not plan:
            reason = "subscription_inactive"
        else:
            usage = await billing_service.usage_in_period(
                db, merchant.id, sub.current_period_start, sub.current_period_end
            )
            if usage["calls_used"] >= plan.max_calls_per_month + sub.bonus_calls:
                reason = "call_limit"
            elif usage["minutes_used"] >= plan.max_minutes_per_month + sub.bonus_minutes:
                reason = "minute_limit"

    if not reason:
        return

    if settings_row.entitlement_mode == "observe":
        audit_service.record(
            db,
            actor_role="system",
            action="entitlement_observe",
            detail=f"পর্যবেক্ষণ মোড — কল অনুমোদিত হয়েছে যদিও: {MESSAGES[reason]}",
            merchant_id=merchant.id,
        )
        await db.commit()
        return

    audit_service.record(
        db,
        actor_role="system",
        action="entitlement_denied",
        detail=f"কল আটকানো হয়েছে: {MESSAGES[reason]}",
        merchant_id=merchant.id,
    )
    await db.commit()
    raise HTTPException(
        status_code=402,
        detail={
            "message": MESSAGES[reason],
            "reason": reason,
            "plan_key": sub.plan_key if sub else None,
            "upgrade_hint": UPGRADE_HINT,
        },
    )
