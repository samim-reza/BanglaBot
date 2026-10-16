"""Carrier callbacks (recording, SMS receipts), calling without telephony configured, and the
admin's operational tools: impersonation, cross-account lists, deleting an account with data."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from tests.e2e.api import OWNER_PASSWORD, admin_token, bearer, client_ip, create_account, fetch, ok, owner_token, salon_catalog
from tests.e2e.fakes import tool_reply
from tests.e2e.phone import booking_day, dial, salon_booking


async def _salon(client, **extra):  # noqa: ANN001, ANN003, ANN202
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", **extra)
    account["catalog"] = await salon_catalog(client, account["headers"])
    account["admin"] = admin
    return account


async def test_recording_and_sms_receipts_land_on_their_rows(app, client, providers, sms_outbox):
    from app.models import CallLog, Message
    from app.services import telnyx_urls

    account = await _salon(client)
    await ok(await client.patch("/api/integrations/sms", json={"enabled": True}, headers=account["headers"]))
    providers.script(tool_reply("save_details", salon_booking(booking_day(13), "09:30", "Rec Order")), tool_reply("end_call"))
    call = await dial(client, app, providers, to=account["merchant"]["inbound_number"], caller="+12125550701", call_sid="v3:e2e-rec")
    await call.says("A haircut with Maya at 9:30, I'm Rec Order")
    await call.says("yes please")
    await call.wraps_up()

    path = urlsplit(telnyx_urls.log_recording_callback_url(call.call_log_id)).path
    assert (await client.post(path.rsplit("/", 1)[0] + "/bad-signature", data={"RecordingSid": "rec-x"})).status_code == 403
    response = await client.post(path, data={"RecordingSid": "rec-e2e-1", "CallSid": call.call_sid, "AccountSid": "e2e-account"})
    assert response.status_code == 204
    [log] = await fetch(CallLog, id=call.call_log_id)
    assert log.recording_sid == "rec-e2e-1"

    # The booking's confirmation text went out (fake Telnyx); its delivery receipts update the row.
    [text] = sms_outbox
    assert text["to"] == "+12125550701" and text["webhook_url"] == ""  # per-message receipts need an https PUBLIC_BASE_URL
    [message] = await fetch(Message, merchant_id=account["merchant"]["id"])
    assert message.status == "sent" and message.kind == "confirmation" and message.provider_sid.startswith("sms-")

    def receipt(status: str) -> str:
        payload = {"id": message.provider_sid, "to": [{"phone_number": text["to"], "status": status}]}
        return json.dumps({"data": {"event_type": "message.finalized", "payload": payload}})

    per_message = urlsplit(telnyx_urls.sms_status_url(message.id)).path
    assert (await client.post(per_message, content=receipt("sending_failed"), headers={"Content-Type": "application/json"})).status_code == 204
    assert (await fetch(Message, id=message.id))[0].status == "failed"
    # The messaging profile's webhook finds the text by Telnyx's id.
    profile = urlsplit(telnyx_urls.sms_events_url()).path
    assert (await client.post(profile, content=receipt("delivered"), headers={"Content-Type": "application/json"})).status_code == 204
    assert (await fetch(Message, id=message.id))[0].status == "delivered"
    assert (await client.post("/telnyx/sms-events/forged", content=receipt("delivered"))).status_code == 403


async def test_calling_out_without_telephony_fails_cleanly(client):
    account = await _salon(client)
    headers = account["headers"]
    record = await ok(await client.post("/api/orders", headers=headers, json={
        "customer_name": "Out Bound", "customer_phone": "+14155550801", "service": "Haircut",
        "catalog_item_id": account["catalog"]["Maya"]["id"], "scheduled_at": f"{booking_day(14)}T10:00",
    }), 201)
    single = await client.post(f"/api/orders/{record['id']}/call", headers=headers)
    assert single.status_code in (409, 422, 500, 503) and "Telnyx" in single.json()["detail"]
    batch = await client.post("/api/orders/call-all", headers=headers, json={})
    assert batch.status_code in (409, 422, 500, 503), batch.text
    status = await ok(await client.get("/api/orders/call-all", headers=headers))
    assert status["run"] is None and status["schedule"] is not None
    [row] = (await ok(await client.get("/api/orders", headers=headers)))["items"]
    assert row["status"] == "pending" and row["call_attempts"] == 0


async def test_admin_impersonates_lists_and_deletes_an_account_with_data(app, client, providers):
    from app.models import CallLog, CatalogItem, Merchant, Order, UsageEvent

    account = await _salon(client)
    admin, merchant_id = account["admin"], account["merchant"]["id"]
    providers.script(tool_reply("save_details", salon_booking(booking_day(15), "11:30", "Del Me")), tool_reply("end_call"))
    call = await dial(client, app, providers, to=account["merchant"]["inbound_number"], caller="+12125550901", call_sid="v3:e2e-del")
    await call.says("A haircut with Maya at 11:30, I'm Del Me")
    await call.says("yes please")
    await call.wraps_up()

    session = await ok(await client.post(f"/api/admin/merchants/{merchant_id}/impersonate", headers=bearer(admin)))
    me = await ok(await client.get("/api/auth/me", headers=bearer(session["token"])))
    assert me["id"] == merchant_id
    orders = await ok(await client.get(f"/api/admin/orders?merchant_id={merchant_id}", headers=bearer(admin)))
    assert orders["total"] == 1 and orders["items"][0]["merchant_name"] == account["merchant"]["business_name"]
    calls = await ok(await client.get(f"/api/admin/calls?merchant_id={merchant_id}&direction=inbound", headers=bearer(admin)))
    assert calls["total"] == 1 and calls["items"][0]["customer_name"] == "Del Me"
    audit = await ok(await client.get(f"/api/admin/audit?merchant_id={merchant_id}&action=admin.*", headers=bearer(admin)))
    assert "admin.impersonate" in {event["action"] for event in audit["items"]}

    # Owner password change: the other sessions end, the returned token keeps working.
    changed = await ok(await client.post("/api/auth/change-password", headers=account["headers"],
                                         json={"current_password": OWNER_PASSWORD, "new_password": "Changed-Pass-e2e-1180!"}))
    assert (await client.get("/api/auth/me", headers=account["headers"])).status_code == 401
    assert (await client.get("/api/auth/me", headers=bearer(changed["token"]))).status_code == 200
    assert (await client.post("/api/auth/login", json={"username": account["username"], "password": OWNER_PASSWORD}, headers=client_ip())).status_code == 401
    assert await owner_token(client, account["username"], "Changed-Pass-e2e-1180!")

    assert (await client.delete(f"/api/admin/merchants/{merchant_id}", headers=bearer(admin))).status_code == 204
    assert not await fetch(Merchant, id=merchant_id)
    assert not await fetch(Order, merchant_id=merchant_id) and not await fetch(CallLog, merchant_id=merchant_id)
    assert not await fetch(CatalogItem, merchant_id=merchant_id)
    assert (await client.get("/api/auth/me", headers=bearer(changed["token"]))).status_code == 401
    # Inbound calls to its old number are no longer routed to it.
    from tests.e2e.phone import answer_inbound

    unrouted = await answer_inbound(client, to=account["merchant"]["inbound_number"], caller="+12125550902", call_sid="v3:e2e-after-delete")
    assert "not in service" in unrouted.text
    # Its usage history (finance) is kept on purpose: the platform paid those providers.
    assert await fetch(UsageEvent, merchant_id=merchant_id)
