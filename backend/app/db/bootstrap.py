"""Create tables and seed the platform admin, settings, plans and trials on startup."""

from loguru import logger
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, engine
from app.models import (
    Base,
    CallCost,
    CallLog,
    CostRate,
    Merchant,
    Plan,
    PlatformAdmin,
    PlatformSettings,
    Subscription,
)
from app.services import billing_service, finance_service

PLAN_SEEDS = [
    {
        "key": "trial",
        "name_bn": "ফ্রি ট্রায়াল",
        "price_monthly": 0,
        "max_calls_per_month": 20,
        "max_minutes_per_month": 60,
        "trial_days": 14,
        "is_default_trial": True,
        "features": [
            "১৪ দিন ফ্রি ট্রায়াল",
            "২০টি কনফার্মেশন কল",
            "বাংলা এআই ভয়েস এজেন্ট",
            "লাইভ ড্যাশবোর্ড",
        ],
        "sort_order": 0,
    },
    {
        "key": "starter",
        "name_bn": "স্টার্টার",
        "price_monthly": 1500,
        "max_calls_per_month": 300,
        "max_minutes_per_month": 900,
        "features": [
            "মাসে ৩০০টি কল",
            "কল ট্রান্সক্রিপ্ট",
            "বাংলা এআই ভয়েস এজেন্ট",
            "ইমেইল সাপোর্ট",
        ],
        "sort_order": 1,
    },
    {
        "key": "growth",
        "name_bn": "গ্রোথ",
        "price_monthly": 4000,
        "max_calls_per_month": 1000,
        "max_minutes_per_month": 3000,
        "features": [
            "মাসে ১০০০টি কল",
            "কল ট্রান্সক্রিপ্ট",
            "অগ্রাধিকার সাপোর্ট",
            "সব ফিচার",
        ],
        "sort_order": 2,
    },
]


async def bootstrap() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Idempotent migrations for databases created before the SaaS port.
    for statement in (
        "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS email VARCHAR(160) NOT NULL DEFAULT ''",
        # Logs are detached (not deleted) with their order so usage metering survives.
        "ALTER TABLE call_logs ALTER COLUMN order_id DROP NOT NULL",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_sid VARCHAR(64) NOT NULL DEFAULT ''",
        "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS custom_greeting VARCHAR(200) NOT NULL DEFAULT ''",
        "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS max_call_seconds INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS voice_tier VARCHAR(20) NOT NULL DEFAULT 'very_basic'",
        "ALTER TABLE merchants ALTER COLUMN voice_tier SET DEFAULT 'very_basic'",
        # Remap merchants still on the first 3-tier catalog; old call-log
        # snapshots keep their keys (billed_secs is already frozen) and are
        # resolved through voice_tiers.LEGACY_ALIASES.
        "UPDATE merchants SET voice_tier='very_basic' WHERE voice_tier='standard'",
        "UPDATE merchants SET voice_tier='basic' WHERE voice_tier='better'",
        "UPDATE merchants SET voice_tier='advance' WHERE voice_tier='best'",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS voice_tier VARCHAR(20) NOT NULL DEFAULT ''",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS billed_secs INTEGER NOT NULL DEFAULT 0",
        # Calls priced before the tier system bill at face value (multiplier 1.0).
        "UPDATE call_logs SET billed_secs = duration_secs WHERE billed_secs = 0 AND duration_secs > 0",
        # Query-shaped composite indexes: usage metering + insights scan call_logs
        # by (merchant, period); order lists filter by (merchant, status) and
        # paginate by (merchant, created_at).
        "CREATE INDEX IF NOT EXISTS ix_call_logs_merchant_created ON call_logs (merchant_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_orders_merchant_status ON orders (merchant_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_orders_merchant_created ON orders (merchant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_created ON audit_logs (created_at DESC)",
    ):
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"migration skipped ({statement.split(' ')[2]}): {exc}")

    settings = get_settings()
    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(
                select(PlatformAdmin).where(PlatformAdmin.username == settings.admin_username)
            )
        ).scalar_one_or_none()
        if not admin:
            db.add(
                PlatformAdmin(
                    username=settings.admin_username,
                    name="Platform Admin",
                    password_hash=hash_password(settings.admin_password),
                )
            )
            await db.commit()
            logger.info(f"Seeded platform admin '{settings.admin_username}'")
        if settings.admin_password == "admin123":
            logger.warning(
                "Platform admin uses the DEFAULT password — set ADMIN_PASSWORD in "
                "backend/.env before exposing this app publicly"
            )

        if not await db.get(PlatformSettings, "default"):
            db.add(PlatformSettings(id="default"))
            await db.commit()
            logger.info("Seeded platform settings")

        seeded_plans = 0
        for seed in PLAN_SEEDS:
            plan = (
                await db.execute(select(Plan).where(Plan.key == seed["key"]))
            ).scalar_one_or_none()
            if not plan:
                db.add(Plan(**seed))
                seeded_plans += 1
        if seeded_plans:
            await db.commit()
            logger.info(f"Seeded {seeded_plans} plans")

        settings_row = await billing_service.get_settings_row(db)
        merchants = (
            await db.execute(
                select(Merchant).where(Merchant.id.not_in(select(Subscription.merchant_id)))
            )
        ).scalars()
        backfilled = 0
        for merchant in merchants:
            await billing_service.start_trial(db, merchant, settings_row)
            backfilled += 1
        if backfilled:
            await db.commit()
            logger.info(f"Backfilled trial subscriptions for {backfilled} merchants")

        # Seed the cost-rate catalog (append-only; only missing keys get a row).
        existing_keys = {
            key for (key,) in (await db.execute(select(CostRate.cost_key).distinct())).all()
        }
        seeded_rates = 0
        for seed in finance_service.RATE_SEEDS:
            if seed["cost_key"] not in existing_keys:
                db.add(CostRate(**seed))
                seeded_rates += 1
        if seeded_rates:
            await db.commit()
            logger.info(f"Seeded {seeded_rates} cost rates")

        # Backfill cost rows for completed calls recorded before the finance engine.
        uncosted = (
            await db.execute(
                select(CallLog).where(
                    CallLog.duration_secs > 0,
                    CallLog.id.not_in(select(CallCost.call_log_id)),
                )
            )
        ).scalars()
        costed = 0
        for log in uncosted:
            if await finance_service.compute_call_cost(db, log):
                costed += 1
        if costed:
            await db.commit()
            logger.info(f"Backfilled costs for {costed} calls")
