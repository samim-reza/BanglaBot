"""Admin system tools: the live-calls view with its hang-up button, system health, the voice
engine tests (on the fake providers), offered verticals, per-account provider chains, and the
talk-to-sales inbox."""

from __future__ import annotations

from tests.e2e.api import admin_token, bearer, client_ip, create_account, fetch, ok, salon_catalog
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import dial
from tests.e2e.telnyx_peer import wait_until


async def test_admin_sees_a_live_call_and_hangs_it_up(app, client, providers):
    from app.models import CallLog

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth")
    await salon_catalog(client, account["headers"])
    call = await dial(client, app, providers, to=account["merchant"]["inbound_number"], caller="+12125551501", call_sid="v3:e2e-live")
    live = await ok(await client.get("/api/admin/live-calls", headers=bearer(admin)))
    [row] = [item for item in live["items"] if item["call_log_id"] == call.call_log_id]
    assert row["merchant_id"] == account["merchant"]["id"] and row["direction"] == "inbound" and "2125551501" not in row["caller"]
    health = await ok(await client.get("/api/admin/system/health", headers=bearer(admin)))
    assert health["database"]["up"] is True and health["live_calls"] >= 1 and health["environment"] == "test"

    await ok(await client.post(f"/api/admin/live-calls/{call.call_log_id}/hangup", headers=bearer(admin)))
    await call.peer.finished(timeout=10.0)
    await settle_background()
    assert (await client.post(f"/api/admin/live-calls/{call.call_log_id}/hangup", headers=bearer(admin))).status_code == 404
    [log] = await fetch(CallLog, id=call.call_log_id)
    assert log.call_status == "completed"
    await wait_until(lambda: call.bridge() is None, what="the bridge to unregister")


async def test_voice_engine_view_and_quick_tests_run_on_the_configured_providers(client, providers):
    from tests.e2e.fakes import text_reply

    admin = await admin_token(client)
    engine = await ok(await client.get("/api/admin/voice-engine", headers=bearer(admin)))
    assert engine
    tts = await client.post("/api/admin/voice-engine/test-tts", json={"text": "Hello there."}, headers=bearer(admin))
    assert tts.status_code == 200, tts.text
    providers.script(text_reply("OK"))
    llm = await client.post("/api/admin/voice-engine/test-llm", headers=bearer(admin))
    assert llm.status_code == 200, llm.text


async def test_offered_verticals_gate_the_signup_catalog(client):
    admin = await admin_token(client)
    current = await ok(await client.get("/api/admin/verticals", headers=bearer(admin)))
    offered = [item["key"] for item in current["items"] if item["offered"]]
    try:
        await ok(await client.put("/api/admin/verticals", json={"offered": ["salon", "clinic"]}, headers=bearer(admin)))
        catalog = await ok(await client.get("/api/public/catalog"))
        assert {v["key"] for v in catalog["verticals"]} == {"salon", "clinic"}
        refused = await client.post("/api/public/signup/quote", json={"tier": "starter", "vertical": "restaurant"})
        assert refused.status_code == 422
    finally:
        await ok(await client.put("/api/admin/verticals", json={"offered": offered}, headers=bearer(admin)))


async def test_per_account_provider_chains_are_admin_only(client):
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", inbound=False)
    merchant_id = account["merchant"]["id"]
    saved = await client.put(f"/api/admin/merchants/{merchant_id}/providers", json={"llm_chain": "gemini:gemini-3.1-flash-lite", "stt_chain": "", "tts_chain": ""}, headers=bearer(admin))
    assert saved.status_code == 200, saved.text
    detail = await ok(await client.get(f"/api/admin/merchants/{merchant_id}", headers=bearer(admin)))
    assert detail["provider_settings"].get("llm_chain") == "gemini:gemini-3.1-flash-lite"
    assert (await client.put(f"/api/admin/merchants/{merchant_id}/providers", json={"llm_chain": "x"}, headers=account["headers"])).status_code in (401, 403)


async def test_talk_to_sales_inquiry_reaches_the_admin_inbox(client):
    from app.models import SalesInquiry

    body = {"name": "Dana Lead", "email": "dana@example.test", "company": "Big Clinic", "business_type": "clinic", "message": "50 doctors"}
    await ok(await client.post("/api/public/contact", json=body, headers=client_ip()), 201)
    assert (await client.post("/api/public/contact", json={"name": "No Contact"}, headers=client_ip())).status_code == 422
    admin = await admin_token(client)
    inbox = await ok(await client.get("/api/admin/inquiries", headers=bearer(admin)))
    [row] = [item for item in inbox["items"] if item["email"] == "dana@example.test"]
    updated = await ok(await client.patch(f"/api/admin/inquiries/{row['id']}", json={"status": "contacted", "admin_notes": "called"}, headers=bearer(admin)))
    assert updated["status"] == "contacted"
    assert (await client.delete(f"/api/admin/inquiries/{row['id']}", headers=bearer(admin))).status_code == 204
    assert not await fetch(SalesInquiry, email="dana@example.test")
