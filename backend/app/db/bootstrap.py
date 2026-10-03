"""Schema on boot: ``create_all`` plus idempotent column patches.

There is no migration tool. ``create_all`` builds missing tables from the
models but never alters an existing one, so every column added after a
table's first deploy is restated below as an ``ADD COLUMN IF NOT EXISTS``.
Everything here must be safe to run repeatedly against an up-to-date database.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.base import Base
from app.db.session import engine
from app.models import AddonRequest, CallLog, CatalogItem, Merchant, Message, Order, SalesInquiry

logger = structlog.get_logger(__name__)

#: Importing the models registers their tables on ``Base.metadata`` for create_all.
REGISTERED_MODELS = (Merchant, Order, CallLog, CatalogItem, SalesInquiry, Message, AddonRequest)

SCHEMA_PATCHES: tuple[str, ...] = (
    # merchants
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS owner_name VARCHAR(120) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS phone VARCHAR(32) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS email VARCHAR(160) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS support_phone VARCHAR(32) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS custom_greeting TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ALTER COLUMN custom_greeting TYPE TEXT",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS language VARCHAR(8) NOT NULL DEFAULT 'bn'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS supported_languages JSONB NOT NULL DEFAULT '[\"bn\", \"en\"]'::jsonb",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS voice_persona VARCHAR(12) NOT NULL DEFAULT 'female'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS verify_address BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS max_call_seconds INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS silence_hangup_secs INTEGER NOT NULL DEFAULT 10",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS auto_call_at TIMESTAMPTZ",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS auto_call_repeat_daily BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE merchants ALTER COLUMN password_hash TYPE VARCHAR(160)",
    # A previous deployment kept verify_address inside a flow_settings JSON blob.
    """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'merchants' AND column_name = 'flow_settings') THEN
            UPDATE merchants SET verify_address = true
            WHERE verify_address = false AND (flow_settings->>'verify_address') = 'true';
        END IF;
    END $$;""",
    # orders — a previous deployment had a courier-only 'rescheduled' status.
    """DO $$ BEGIN
        IF to_regtype('banglabot_order_status') IS NOT NULL THEN
            UPDATE orders SET status = 'needs_review' WHERE status::text = 'rescheduled';
        END IF;
    END $$;""",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_ref VARCHAR(60) NOT NULL DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS address TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS items_summary TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'BDT'",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS flow_data JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS call_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS last_call_at TIMESTAMPTZ",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()",
    "CREATE INDEX IF NOT EXISTS ix_orders_merchant_status ON orders (merchant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_orders_merchant_created ON orders (merchant_id, created_at DESC)",
    # call_logs
    "ALTER TABLE call_logs ALTER COLUMN order_id DROP NOT NULL",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_sid VARCHAR(64) NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS outcome VARCHAR(32) NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS transcript TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS language VARCHAR(8) NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS duration_secs INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS final_node VARCHAR(32) NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS llm_prompt_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS llm_completion_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS tts_chars INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS tts_cache_hits INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_call_logs_merchant_created ON call_logs (merchant_id, created_at DESC)",
    # --- multi-vertical platform (2026-10) ---------------------------------------
    # Accounts that existed before regions were Bangladeshi: the first ADD fills
    # them with BD values, then the default moves to the international preset.
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS vertical VARCHAR(32) NOT NULL DEFAULT 'ecommerce'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS vertical_config JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS knowledge TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS inbound_number VARCHAR(32) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS region VARCHAR(8) NOT NULL DEFAULT 'BD'",
    "ALTER TABLE merchants ALTER COLUMN region SET DEFAULT 'INTL'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Dhaka'",
    "ALTER TABLE merchants ALTER COLUMN timezone SET DEFAULT 'UTC'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'BDT'",
    "ALTER TABLE merchants ALTER COLUMN currency SET DEFAULT 'USD'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS emergency_number VARCHAR(16) NOT NULL DEFAULT '999'",
    "ALTER TABLE merchants ALTER COLUMN emergency_number SET DEFAULT '112'",
    "ALTER TABLE merchants ALTER COLUMN language SET DEFAULT 'en'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS plan VARCHAR(24) NOT NULL DEFAULT 'trial'",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS widget_enabled BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS widget_key VARCHAR(40) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS widget_settings JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(64) NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS ix_merchants_vertical ON merchants (vertical)",
    "CREATE INDEX IF NOT EXISTS ix_merchants_inbound_number ON merchants (inbound_number)",
    "CREATE INDEX IF NOT EXISTS ix_merchants_widget_key ON merchants (widget_key)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS kind VARCHAR(24) NOT NULL DEFAULT 'order'",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'manual'",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS catalog_item_id VARCHAR REFERENCES catalog_items(id) ON DELETE SET NULL",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE orders ALTER COLUMN currency SET DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS ix_orders_merchant_scheduled ON orders (merchant_id, scheduled_at)",
    "CREATE INDEX IF NOT EXISTS ix_orders_catalog_item_id ON orders (catalog_item_id)",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS direction VARCHAR(10) NOT NULL DEFAULT 'outbound'",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS flow VARCHAR(40) NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS caller_number VARCHAR(32) NOT NULL DEFAULT ''",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS llm_cached_tokens INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_call_logs_merchant_direction ON call_logs (merchant_id, direction, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_catalog_items_merchant_kind ON catalog_items (merchant_id, kind, sort_order)",
    # --- SMS + calendar sync (2026-10) ------------------------------------------------
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS sms_settings JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS calendar_token VARCHAR(48) NOT NULL DEFAULT ''",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS calendar_settings JSONB NOT NULL DEFAULT '{}'::jsonb",
    "CREATE INDEX IF NOT EXISTS ix_merchants_calendar_token ON merchants (calendar_token)",
    "CREATE INDEX IF NOT EXISTS ix_messages_merchant_created ON messages (merchant_id, created_at DESC)",
    # --- Add-ons + chat channels (2026-10) ----------------------------------------------
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS addons JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE merchants ADD COLUMN IF NOT EXISTS channel_settings JSONB NOT NULL DEFAULT '{}'::jsonb",
    # Accounts from before add-ons existed keep the website chat they already had on.
    (
        "UPDATE merchants SET addons = CASE WHEN widget_enabled AND plan NOT IN ('trial', 'enterprise', 'chat') "
        "THEN '{\"_v\": 1, \"web_chat\": 1}'::jsonb ELSE '{\"_v\": 1}'::jsonb || addons END "
        "WHERE addons->'_v' IS NULL"
    ),
    "ALTER TABLE merchants ALTER COLUMN addons SET DEFAULT '{\"_v\": 1}'::jsonb",
    "CREATE INDEX IF NOT EXISTS ix_merchants_whatsapp ON merchants ((channel_settings->'whatsapp'->>'number'))",
    "CREATE INDEX IF NOT EXISTS ix_merchants_messenger ON merchants ((channel_settings->'messenger'->>'page_id'))",
    "CREATE INDEX IF NOT EXISTS ix_addon_requests_status ON addon_requests (status, created_at DESC)",
)


async def apply_schema_patches(conn: AsyncConnection) -> None:
    for statement in SCHEMA_PATCHES:
        await conn.execute(text(statement))


async def create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_schema_patches(conn)


async def bootstrap() -> None:
    """Called from the app lifespan: schema and idempotent patches. No demo data in production —
    accounts are created in the admin console (``scripts/create_merchant.py`` for the terminal)."""
    await create_schema()
