"""After the run's calls, chats and payments: the finance console reflects the traffic, and one
tick of each background job works on the data that now exists (reminder texts, holds, SMS
metering, subscription sweep)."""

from __future__ import annotations

from datetime import timedelta

from tests.e2e.api import admin_token, bearer, create_account, fetch, ok, salon_catalog
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day


async def test_finance_console_reflects_the_traffic(client):
    admin = await admin_token(client)
    overview = await ok(await client.get("/api/admin/finance/overview", headers=bearer(admin)))
    assert overview["calls"] >= 1 and overview["chats"] >= 1 and overview["cost_usd"] > 0, overview
    by_category = await ok(await client.get("/api/admin/finance/breakdown?by=category", headers=bearer(admin)))
    assert {"llm", "stt", "tts"} <= {item["key"] for item in by_category["items"]}, by_category
    accounts = await ok(await client.get("/api/admin/finance/accounts?limit=100", headers=bearer(admin)))
    assert any(row["calls"] >= 1 for row in accounts["items"])
    export = await client.get("/api/admin/finance/export.csv", headers=bearer(admin))
    assert export.status_code == 200 and len(export.text.splitlines()) > 1


async def test_reminder_texts_go_out_once_for_upcoming_bookings(client, sms_outbox):
    from app.models import Message, Order
    from app.services.sms.reminders import send_due_reminders

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", inbound=False)
    headers = account["headers"]
    catalog = await salon_catalog(client, headers)
    await ok(await client.patch("/api/integrations/sms", json={"enabled": True, "reminder_hours": 24}, headers=headers))
    record = await ok(await client.post("/api/orders", headers=headers, json={
        "customer_name": "Remi Nder", "customer_phone": "+14155550990", "service": "Haircut", "catalog_item_id": catalog["Maya"]["id"],
        "scheduled_at": f"{booking_day(3)}T10:00",
    }), 201)
    [row] = await fetch(Order, id=record["id"])
    # The reminder sender runs 12 h before the appointment (booked days earlier).
    sent = await send_due_reminders(now=row.scheduled_at - timedelta(hours=12))
    assert sent >= 1
    mine = [text for text in sms_outbox if text["to"] == "+14155550990"]
    assert len(mine) == 1 and mine[0]["text"].startswith("Reminder from"), mine
    assert "Haircut with Maya" in mine[0]["text"], mine
    await send_due_reminders(now=row.scheduled_at - timedelta(hours=11))
    assert len([text for text in sms_outbox if text["to"] == "+14155550990"]) == 1  # reminded once
    [message] = [m for m in await fetch(Message, merchant_id=account["merchant"]["id"]) if m.kind == "reminder"]
    assert message.status == "sent"
    await settle_background()


async def test_background_jobs_tick_on_real_data(client):
    from app.db.session import AsyncSessionLocal
    from app.finance import guard, sms_meter
    from app.services import billing_jobs
    from app.services.payments import holds

    counts = await billing_jobs.sweep_once()
    assert isinstance(counts, dict)
    swept = await holds.sweep()
    assert isinstance(swept, dict)
    async with AsyncSessionLocal() as session:
        metered = await sms_meter.meter_sent_sms(session)
        assert metered >= 0
        await guard.refresh(session)
