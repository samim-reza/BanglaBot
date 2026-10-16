"""The website chat widget: add-on requested + approved, widget switched on, a visitor books
through the public endpoints with the widget key, the booking lands in Postgres."""

from __future__ import annotations

from tests.e2e.api import fetch, ok, salon_with_widget
from tests.e2e.fakes import tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day, salon_booking


async def test_visitor_books_through_the_widget(client, providers, webhooks):
    from app.models import CallLog, Order

    account = await salon_with_widget(client)
    key = account["merchant"]["widget_key"]
    await ok(await client.patch("/api/auth/me", json={"webhook_url": "https://hooks.example.test/chat"}, headers=account["headers"]))

    config = await ok(await client.get(f"/api/public/widget/{key}/config"))
    assert config == {"enabled": True, "title": "Chat with Glow", "subtitle": "", "color": "#112233", "position": "right"}
    script = await client.get("/api/public/widget.js")
    assert script.status_code == 200 and script.headers["access-control-allow-origin"] == "*"

    day = booking_day(4)
    providers.script(
        tool_reply("save_details", salon_booking(day, "14:00", "Lee Park")), tool_reply("save_details", {"phone": "4155550123"}), tool_reply("end_call"),
    )
    start = await ok(await client.post(f"/api/public/widget/{key}/start", headers={"Origin": "https://customer-site.example"}))
    session_id = start["session_id"]
    assert start["messages"][0].startswith("Hi, welcome to")
    said = await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": "A haircut with Maya at 2pm, I'm Lee Park"}))
    assert "number" in said["messages"][-1] and said["ended"] is False  # a chat has no caller id
    said = await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": "415 555 0123"}))
    assert "Shall I book it?" in said["messages"][-1] and said["ended"] is False
    done = await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": "yes please"}))
    # A chat stays open after the booking (the visitor may ask more); "that's all" ends it.
    assert done["ended"] is False and done["messages"][-1].startswith("You're all set"), done
    bye = await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": "No, that's all, thanks. Bye!"}))
    assert bye["ended"] is True, bye
    assert not await settle_background()

    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    assert record.source == "website_chat" and record.status.value == "confirmed" and record.customer_name == "Lee Park"
    assert record.customer_phone.endswith("4155550123") and record.scheduled_at is not None
    [log] = await fetch(CallLog, merchant_id=account["merchant"]["id"])
    assert log.direction == "widget" and log.outcome == "booked" and log.order_id == record.id and log.call_status == "completed"
    assert "Customer: yes please" in log.transcript
    assert not webhooks.errors, webhooks.errors[0]
    assert webhooks.bodies() and webhooks.bodies()[-1]["record"]["id"] == record.id

    # The finished chat answers "start a new one"; another site's key never reaches it.
    ended = await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": "hello?"})
    assert ended.status_code == 200 and ended.json()["messages"] == []
    wrong = await client.post("/api/public/widget/not-the-key/say", json={"session_id": session_id, "text": "hi"})
    assert wrong.status_code == 404


async def test_widget_is_closed_when_switched_off_or_unknown(client, providers):
    account = await salon_with_widget(client)
    key = account["merchant"]["widget_key"]
    await ok(await client.patch("/api/auth/me", json={"widget_enabled": False}, headers=account["headers"]))
    assert (await ok(await client.get(f"/api/public/widget/{key}/config")))["enabled"] is False
    assert (await client.post(f"/api/public/widget/{key}/start")).status_code == 404
    assert (await client.post("/api/public/widget/unknown-key/start")).status_code == 404
