"""Smaller owner / admin tools: the webhook test button, rotating the widget key and the
webhook secret, the admin's add-on editor, a manual SMS for a record, signing out everywhere."""

from __future__ import annotations

from tests.e2e.api import bearer, fetch, ok, salon_with_widget
from tests.e2e.phone import booking_day


async def test_webhook_test_button_and_secret_rotation(client, webhooks):
    from app.services import webhook_service

    account = await salon_with_widget(client)
    headers = account["headers"]
    assert (await client.post("/api/auth/me/webhook-test", headers=headers)).status_code == 422  # no URL yet
    me = await ok(await client.patch("/api/auth/me", json={"webhook_url": "https://hooks.example.test/test"}, headers=headers))
    result = await ok(await client.post("/api/auth/me/webhook-test", headers=headers))
    assert result == {"ok": True, "status": 200}, (result, webhooks.errors)
    [request] = webhooks.requests
    assert webhooks.bodies()[0]["event"] == "test"
    assert request.headers["X-Agent-Signature"] == webhook_service.sign(me["webhook_secret"], request.content)
    rotated = await ok(await client.post("/api/auth/me/webhook-secret", headers=headers))
    assert rotated["webhook_secret"] != me["webhook_secret"] and len(rotated["webhook_secret"]) >= 32
    # A private address is refused when saved (and never fetched).
    refused = await client.patch("/api/auth/me", json={"webhook_url": "http://10.0.0.5/hook"}, headers=headers)
    assert refused.status_code == 422 and len(webhooks.requests) == 1


async def test_rotating_the_widget_key_retires_the_old_snippet(client):
    account = await salon_with_widget(client)
    old = account["merchant"]["widget_key"]
    rotated = await ok(await client.post("/api/auth/me/widget-key", headers=account["headers"]))
    assert rotated["widget_key"] != old
    assert (await ok(await client.get(f"/api/public/widget/{old}/config")))["enabled"] is False
    assert (await ok(await client.get(f"/api/public/widget/{rotated['widget_key']}/config")))["enabled"] is True


async def test_admin_sets_addons_directly_and_entitlements_follow(client):
    from tests.e2e.api import admin_token, create_account

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="starter", inbound=False)
    merchant_id = account["merchant"]["id"]
    assert (await client.put(f"/api/admin/merchants/{merchant_id}/addons", json={"addons": {"teleporter": 1}}, headers=bearer(admin))).status_code == 422
    saved = await ok(await client.put(f"/api/admin/merchants/{merchant_id}/addons", json={"addons": {"web_chat": 1, "minutes": 2}}, headers=bearer(admin)))
    assert saved["merchant"]["addons"] == {"web_chat": 1, "minutes": 2}
    assert "web_chat" in saved["entitlements"]["channels"] and saved["entitlements"]["limits"]["minutes"] == 150 + 200
    me = await ok(await client.patch("/api/auth/me", json={"widget_enabled": True}, headers=account["headers"]))
    assert me["widget_enabled"] is True and me["widget_key"]


async def test_manual_sms_for_a_record_and_signing_out_everywhere(client, sms_outbox):
    from app.models import Message

    account = await salon_with_widget(client)
    headers = account["headers"]
    staff = (await ok(await client.get("/api/catalog?kind=staff", headers=headers)))[0]
    record = await ok(await client.post("/api/orders", headers=headers, json={
        "customer_name": "Sam Text", "customer_phone": "+14155550311", "service": "Haircut", "catalog_item_id": staff["id"],
        "scheduled_at": f"{booking_day(6)}T14:00",
    }), 201)
    standard = await ok(await client.post(f"/api/integrations/messages/order/{record['id']}", json={}, headers=headers))
    assert standard["status"] == "sent" and "your Haircut with Maya is booked for" in standard["body"], standard
    custom = await ok(await client.post(f"/api/integrations/messages/order/{record['id']}", json={"body": "Running 10 min late, sorry!"}, headers=headers))
    assert custom["body"] == "Running 10 min late, sorry!" and [m["to"] for m in sms_outbox] == ["+14155550311"] * 2
    listed = await ok(await client.get(f"/api/integrations/messages?order_id={record['id']}", headers=headers))
    assert listed["total"] == 2 and len(await fetch(Message, order_id=record["id"])) == 2

    fresh = await ok(await client.post("/api/auth/logout-all", headers=headers))
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
    assert (await client.get("/api/auth/me", headers=bearer(fresh["token"]))).status_code == 200


async def test_a_chat_only_plan_does_not_take_phone_calls(client):
    from tests.e2e.api import admin_token, create_account
    from tests.e2e.phone import answer_inbound

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="chat")
    answered = await answer_inbound(client, to=account["merchant"]["inbound_number"], caller="+12125551701", call_sid="v3:e2e-chat-plan")
    assert "not taking calls" in answered.text and "<Stream" not in answered.text
    order = await ok(await client.post("/api/orders", headers=account["headers"], json={
        "customer_name": "No Calls", "customer_phone": "+14155550312", "service": "Haircut", "scheduled_at": f"{booking_day(6)}T15:00",
    }), 201)
    refused = await client.post(f"/api/orders/{order['id']}/call", headers=account["headers"])
    assert refused.status_code == 403
