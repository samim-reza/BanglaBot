"""Platform boot on an empty database: schema, idempotent patches, env superadmin, background jobs."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from tests.e2e.api import admin_token, bearer, fetch, ok
from tests.e2e.env import ADMIN_USERNAME
from tests.e2e.fixtures import LIFESPAN_TASKS

EXPECTED_TABLES = {
    "merchants", "orders", "call_logs", "catalog_items", "sales_inquiries", "messages", "addon_requests", "admin_users",
    "audit_events", "payments", "platform_settings", "usage_events", "usage_daily", "subscriptions", "signups",
}


async def test_boot_creates_the_schema_and_seeds_the_env_superadmin(app, client):
    from app.db.session import engine
    from app.models import AdminUser

    async with engine.connect() as conn:
        tables = set((await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))).scalars())
    assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"
    admins = await fetch(AdminUser)
    assert [(row.username, row.role) for row in admins] == [(ADMIN_USERNAME, "superadmin")]
    health = await ok(await client.get("/health"))
    assert health["status"] == "ok" and health["redis"] == {"status": "disabled"}
    # Every background loop of the lifespan is alive.
    running = {task.get_name() for task in asyncio.all_tasks() if not task.done()}
    assert LIFESPAN_TASKS <= running, f"background loops not running: {LIFESPAN_TASKS - running}"


async def test_bootstrap_is_idempotent_on_an_up_to_date_database(app):
    from app.db import bootstrap

    await bootstrap.bootstrap()  # second run: every patch must be a no-op, no duplicate admin
    from app.models import AdminUser

    assert len(await fetch(AdminUser)) == 1


async def test_one_tick_of_every_background_job_runs_on_real_sql(app):
    """The loops swallow their errors to stay alive, so each job's body is called directly here."""
    from app.db.session import AsyncSessionLocal
    from app.finance import guard, sms_meter
    from app.finance import scheduler as finance_scheduler
    from app.services import billing_jobs, catalog_plans
    from app.services.dialer.schedule import fire_due_schedules
    from app.services.payments import holds
    from app.services.sms.reminders import send_due_reminders
    from app.voice import text_session

    assert await fire_due_schedules() == 0
    assert await send_due_reminders() == 0
    assert await billing_jobs.sweep_once() is not None
    assert await holds.sweep() is not None
    await catalog_plans.ensure_fresh(max_age=0)
    await text_session.reap()
    async with AsyncSessionLocal() as session:
        assert await sms_meter.meter_sent_sms(session) == 0
        await guard.refresh(session)
        assert await finance_scheduler._prune(session) == 0


async def test_admin_can_sign_in_with_the_seeded_account(client):
    token = await admin_token(client)
    me = await ok(await client.get("/api/admin/users/me", headers=bearer(token)))
    assert me["username"] == ADMIN_USERNAME and me["role"] == "superadmin"
