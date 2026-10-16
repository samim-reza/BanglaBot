"""Owner portal, continued: the call-flow editor (save / preview / stale hash / reset) under
admin locks and plan limits, a plan upgrade paid through the dummy checkout, and add-on
requests the admin approves or declines."""

from __future__ import annotations

from urllib.parse import urlsplit

from tests.e2e.api import admin_token, bearer, create_account, fetch, ok, salon_catalog
from tests.e2e.phone import dial

GREETING = "Hi, you've reached {business}."
LOCKED = "Thanks for calling {business}. This call may be recorded."


def _greeting(text: str) -> dict:
    return {"steps": {"greet": {"lines": {"en": {"greeting": text}}}}}


async def test_flow_editor_save_preview_stale_hash_and_the_call_uses_it(app, client, providers):
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth")
    headers, name = account["headers"], account["merchant"]["business_name"]
    await salon_catalog(client, headers)
    flow = await ok(await client.get("/api/agent/flow", headers=headers))
    assert flow["vertical"] == "salon" and flow["editing"] == "full" and "inbound" in flow["directions"]

    preview = await ok(await client.post("/api/agent/flow/preview", json={"config": _greeting(GREETING)}, headers=headers))
    assert preview["directions"]["inbound"]["opening"].startswith(f"Hi, you've reached {name}.")
    saved = await ok(await client.put("/api/agent/flow", json={"config": _greeting(GREETING), "base_hash": flow["hash"]}, headers=headers))
    assert saved["config"]["steps"]["greet"]["lines"]["en"]["greeting"] == GREETING and saved["hash"] != flow["hash"]
    stale = await client.put("/api/agent/flow", json={"config": _greeting("Hello again."), "base_hash": flow["hash"]}, headers=headers)
    assert stale.status_code == 409
    unknown = await client.put("/api/agent/flow", json={"config": {"steps": {"teleport": {"enabled": True}}}}, headers=headers)
    assert unknown.status_code == 422 and unknown.json()["detail"]["errors"][0]["path"] == "steps.teleport"

    # The next phone call opens with the owner's wording.
    providers.script()
    call = await dial(client, app, providers, to=account["merchant"]["inbound_number"], caller="+12125550401", call_sid="v3:e2e-greeting")
    assert call.agent_lines()[0].startswith(f"Hi, you've reached {name}."), call.agent_lines()
    await call.peer.stop()
    await call.peer.finished(timeout=10.0)


async def test_admin_locks_bind_the_owner_and_survive_a_reset(client):
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", inbound=False)
    merchant_id, headers, name = account["merchant"]["id"], account["headers"], account["merchant"]["business_name"]
    locked = await ok(await client.put(f"/api/admin/merchants/{merchant_id}/agent-flow-locks", json={"locks": {"steps.greet.lines.en.greeting": LOCKED}}, headers=bearer(admin)))
    assert "steps.greet.lines.en.greeting" in locked["locked"]

    flow = await ok(await client.get("/api/agent/flow", headers=headers))
    assert flow["locked"] == ["steps.greet.lines.en.greeting"]
    refused = await client.put("/api/agent/flow", json={"config": _greeting(GREETING), "base_hash": flow["hash"]}, headers=headers)
    assert refused.status_code == 422 and "steps.greet.lines.en.greeting" in refused.json()["detail"]["locked"]
    # Other lines stay editable.
    ok_edit = {"steps": {"farewell": {"lines": {"en": {"farewell": "Thanks, see you soon!"}}}}}
    await ok(await client.put("/api/agent/flow", json={"config": ok_edit, "base_hash": flow["hash"]}, headers=headers))
    reset = await ok(await client.post("/api/agent/flow/reset", headers=headers))
    assert not reset["config"].get("steps") and reset["locked"] == ["steps.greet.lines.en.greeting"]
    preview = await ok(await client.post("/api/agent/flow/preview", json={}, headers=headers))
    assert preview["directions"]["inbound"]["opening"].startswith(f"Thanks for calling {name}. This call may be recorded.")
    # Support admins may edit the owner's flow, only superadmins set locks.
    view = await ok(await client.get(f"/api/admin/merchants/{merchant_id}/agent-flow", headers=bearer(admin)))
    assert view["locked"] == ["steps.greet.lines.en.greeting"]


async def test_plan_limits_on_the_flow_editor(client):
    admin = await admin_token(client)
    starter = await create_account(client, admin, vertical="salon", plan="starter", inbound=False)
    flow = await ok(await client.get("/api/agent/flow", headers=starter["headers"]))
    assert flow["editing"] == "lines"
    payment = {"steps": {"payment": {"enabled": True, "options": {"mode": "online_required"}}}}
    refused = await client.put("/api/agent/flow", json={"config": payment}, headers=starter["headers"])
    assert refused.status_code == 422
    await ok(await client.put("/api/agent/flow", json={"config": _greeting(GREETING)}, headers=starter["headers"]))


async def test_plan_upgrade_is_paid_through_checkout_and_takes_effect(client):
    from app.models import Merchant, Subscription

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="starter", inbound=False)
    headers, merchant_id = account["headers"], account["merchant"]["id"]
    quote = await ok(await client.post("/api/plan/quote", json={"tier": "growth", "interval": "month", "addons": {"sms": 2}}, headers=headers))
    assert float(quote["quote"]["total"]) == 169.0, quote
    change = await ok(await client.post("/api/plan/change", json={"tier": "growth", "interval": "month", "addons": {"sms": 2}}, headers=headers))
    assert change["checkout_url"].startswith("http://portal.test/pay/")
    assert (await fetch(Merchant, id=merchant_id))[0].plan == "starter"  # nothing changes before payment

    token = urlsplit(change["checkout_url"]).path.removeprefix("/pay/")
    paid = await ok(await client.post(f"/api/public/pay/{token}/complete"))
    assert paid["status"] == "paid" and paid["return_url"].startswith("http://portal.test/plan")
    [merchant] = await fetch(Merchant, id=merchant_id)
    assert merchant.plan == "growth" and merchant.addons.get("sms") == 2
    [sub] = await fetch(Subscription, id=change["subscription_id"])
    assert sub.status == "active" and sub.tier == "growth"
    view = await ok(await client.get("/api/plan", headers=headers))
    assert view["tier"]["key"] == "growth" and view["subscription"]["status"] == "active"
    assert (await client.post("/api/plan/change", json={"tier": "growth", "interval": "month", "addons": {"sms": 2}}, headers=headers)).status_code == 409
    cancelled = await ok(await client.post("/api/plan/cancel", headers=headers))
    assert cancelled["cancel_at_period_end"] is True
    resumed = await ok(await client.delete("/api/plan/cancel", headers=headers))
    assert resumed["cancel_at_period_end"] is False


async def test_addon_requests_are_declined_or_cancelled(client):
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", inbound=False)
    headers = account["headers"]
    shop = await ok(await client.get("/api/addons", headers=headers))
    assert "whatsapp" in shop["available"] and "web_chat" in shop["available"]
    assert (await client.post("/api/addons/requests", json={"addon": "teleporter"}, headers=headers)).status_code == 422
    shop = await ok(await client.post("/api/addons/requests", json={"addon": "whatsapp"}, headers=headers), 201)
    [request] = [row for row in shop["requests"] if row["addon"] == "whatsapp"]
    pending = await ok(await client.get("/api/admin/addon-requests?status=pending", headers=bearer(admin)))
    assert request["id"] in {row["id"] for row in pending["items"]}
    declined = await ok(await client.post(f"/api/admin/addon-requests/{request['id']}/decline", json={"admin_note": "not yet"}, headers=bearer(admin)))
    assert declined["status"] == "declined"
    assert (await client.post(f"/api/admin/addon-requests/{request['id']}/approve", json={}, headers=bearer(admin))).status_code == 409
    me = await ok(await client.get("/api/auth/me", headers=headers))
    assert "whatsapp" not in me["addons"]

    shop = await ok(await client.post("/api/addons/requests", json={"addon": "minutes", "quantity": 3}, headers=headers), 201)
    [request] = [row for row in shop["requests"] if row["addon"] == "minutes"]
    assert request["quantity"] == 3
    shop = await ok(await client.delete(f"/api/addons/requests/{request['id']}", headers=headers))
    assert [row["status"] for row in shop["requests"] if row["id"] == request["id"]] == ["cancelled"]
