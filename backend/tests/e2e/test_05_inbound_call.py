"""An inbound phone call end to end: Telnyx webhook → TeXML with a signed stream → media
websocket (connected / start / media / stop) → fake STT → scripted model → booking in
Postgres → call log, usage ledger, SMS, signed owner webhook, iCal feed → no second
conversation when Telnyx re-opens the stream of a finished call."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.e2e.api import admin_token, create_account, fetch, ok, salon_catalog
from tests.e2e.fakes import tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import answer_inbound, booking_day, dial, salon_booking
from tests.e2e.telnyx_peer import TelnyxMediaPeer, wait_until

CALLER = "+12125550111"
HOOK = "https://hooks.example.test/callisa"


async def _salon(client, **extra):  # noqa: ANN001, ANN003
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", **extra)
    account["catalog"] = await salon_catalog(client, account["headers"])
    return account


async def test_inbound_call_books_and_everything_downstream_happens(app, client, providers, webhooks):
    from app.models import CallLog, Merchant, Message, Order, UsageEvent
    from app.services import sms_service, webhook_service

    account = await _salon(client)
    merchant, headers = account["merchant"], account["headers"]
    owner = await ok(await client.patch("/api/auth/me", json={"webhook_url": HOOK}, headers=headers))
    secret = owner["webhook_secret"]
    assert len(secret) >= 32
    feed = (await ok(await client.post("/api/integrations/calendar/feed-token", headers=headers)))["calendar"]["feed_url"]

    day = booking_day()
    providers.script(tool_reply("save_details", salon_booking(day)), tool_reply("end_call"))
    call = await dial(client, app, providers, to=merchant["inbound_number"], caller=CALLER, call_sid="v3:e2e-call-1")
    assert call.agent_lines()[0].startswith("Hello, thank you for calling")
    await call.says("Hi, a haircut with Maya at 11 please, I'm Ana Lopez")
    readback = call.agent_lines()[-1]
    assert "Haircut with Maya" in readback and "Shall I book it?" in readback, call.agent_lines()
    await call.says("yes please")
    assert any(line.startswith("You're all set") for line in call.agent_lines()), call.agent_lines()
    await call.wraps_up()
    assert call.peer.audio_frames() > 0 and call.peer.marks()[0] == "agent-1"
    assert not providers.llms[-1].exhausted
    leftovers = await settle_background()
    assert not leftovers, leftovers

    # --- the booking, in Postgres ---
    [record] = await fetch(Order, merchant_id=merchant["id"])
    start = datetime.fromisoformat(f"{day}T11:00").replace(tzinfo=ZoneInfo("America/New_York"))
    assert record.kind == "booking" and record.status.value == "confirmed" and record.source == "inbound_call"
    assert record.scheduled_at == start and record.catalog_item_id == account["catalog"]["Maya"]["id"]
    assert record.customer_name == "Ana Lopez" and record.customer_phone == CALLER and float(record.total_amount) == 45.0
    assert record.details["service"] == "Haircut" and record.details["idem"]

    # --- the call log: transcript, outcome, usage counters ---
    [log] = await fetch(CallLog, merchant_id=merchant["id"])
    assert log.id == call.call_log_id and log.direction == "inbound" and log.order_id == record.id
    assert log.outcome == "booked" and log.call_status == "completed" and log.caller_number == CALLER
    assert log.transcript.startswith("Agent: Hello") and "Customer: yes please" in log.transcript
    assert log.llm_prompt_tokens >= 900 and log.llm_completion_tokens >= 40 and log.tts_chars > 0
    assert log.twilio_call_sid  # remembered from the stream's call_control_id

    # --- the usage ledger (finance) ---
    lines = await fetch(UsageEvent, call_log_id=log.id)
    categories = {line.category for line in lines}
    assert {"llm", "stt", "tts"} <= categories, categories
    assert all(line.merchant_id == merchant["id"] for line in lines)

    # --- SMS: composed from the record, nothing sent while the platform has SMS off ---
    assert not sms_service.platform_ready() and not await fetch(Message, merchant_id=merchant["id"])
    from app.services.sms.composer import compose

    [row] = await fetch(Merchant, id=merchant["id"])
    body = compose("confirmation", record, row, item_name="Maya")  # item_name = the record's catalog item (the stylist)
    assert "your Haircut with Maya is booked for" in body and "11 AM" in body, body

    # --- the owner's webhook: one signed call.completed event ---
    assert not webhooks.errors, webhooks.errors[0]
    [request] = webhooks.requests
    # Pinned to the vetted address; the Host header keeps the owner's name.
    assert request.url.path == "/callisa" and request.url.host == webhooks.PUBLIC_IP and request.headers["host"] == "hooks.example.test"
    assert request.headers["X-Agent-Signature"] == webhook_service.sign(secret, request.content)
    payload = webhooks.bodies()[0]
    assert payload["event"] == "call.completed" and payload["call"]["id"] == log.id and payload["call"]["outcome"] == "booked"
    assert payload["record"]["id"] == record.id and payload["record"]["status"] == "confirmed"

    # --- the iCal feed lists it ---
    ics = await client.get(feed.removeprefix("http://testserver"))
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert ics.text.count("BEGIN:VEVENT") == 1 and "Haircut" in ics.text and start.strftime("%Y%m%d") in ics.text

    # --- portal views of the call ---
    calls = await ok(await client.get("/api/calls", headers=headers))
    assert calls["items"][0]["id"] == log.id and calls["items"][0]["outcome"] == "booked"
    detail = await ok(await client.get(f"/api/orders/{record.id}", headers=headers))
    assert detail["call_logs"][0]["id"] == log.id
    usage = (await ok(await client.get("/api/auth/workspace", headers=headers)))["usage"]
    assert usage["calls"] == 1 and usage["minutes"] >= 0 and usage["chats"] == 0, usage
    admin = await admin_token(client)
    costs = await ok(await client.get(f"/api/admin/finance/calls/{log.id}/costs", headers={"Authorization": f"Bearer {admin}"}))
    assert costs["lines"], costs

    # --- Telnyx re-opens the stream of the finished call: no second conversation ---
    llms, stts = len(providers.llms), len(providers.stts)
    again = TelnyxMediaPeer(app, call.answer.url)
    await again.open()
    await again.start(call.answer.parameters, call_control_id=call.call_sid, caller=CALLER, called=merchant["inbound_number"])
    await again.finished(timeout=5.0)
    assert again.closed.is_set() and again.audio_frames() == 0
    assert (len(providers.llms), len(providers.stts)) == (llms, stts)
    assert len(await fetch(Order, merchant_id=merchant["id"])) == 1


async def test_media_socket_refuses_bad_tokens_and_unknown_numbers_get_a_polite_hangup(app, client, providers):
    account = await _salon(client)
    unrouted = await answer_inbound(client, to="+19995550000", caller=CALLER, call_sid="v3:e2e-nobody")
    assert unrouted.status_code == 200 and "not in service" in unrouted.text and "<Hangup/>" in unrouted.text
    bad_sig = await client.post("/telnyx/inbound/not-a-signature", data={"To": account["merchant"]["inbound_number"]})
    assert bad_sig.status_code == 403

    response = await answer_inbound(client, to=account["merchant"]["inbound_number"], caller=CALLER, call_sid="v3:e2e-forged")
    from tests.e2e.telnyx_peer import parse_stream

    answer = parse_stream(response.text)
    forged = dict(answer.parameters, media_token=answer.parameters["media_token"][:-3] + "abc")
    peer = TelnyxMediaPeer(app, answer.url)
    await peer.open()
    await peer.start(forged)
    await peer.finished(timeout=5.0)
    assert peer.close_code == 1008 and not providers.stts
    other = dict(answer.parameters, call_log_id="someone-elses-call")
    peer = TelnyxMediaPeer(app, answer.url)
    await peer.open()
    await peer.start(other)
    await peer.finished(timeout=5.0)
    assert peer.close_code == 1008 and not providers.stts


async def test_caller_hangs_up_mid_call_and_the_log_is_settled(app, client, providers):
    from app.models import CallLog, Order

    account = await _salon(client)
    providers.script()
    call = await dial(client, app, providers, to=account["merchant"]["inbound_number"], caller=CALLER, call_sid="v3:e2e-hangup")
    await call.peer.stop()  # Telnyx: the caller hung up
    await call.peer.finished(timeout=10.0)
    await settle_background()
    [log] = await fetch(CallLog, id=call.call_log_id)
    assert log.call_status == "completed" and log.outcome and log.transcript.startswith("Agent: Hello")
    assert not await fetch(Order, merchant_id=account["merchant"]["id"])
    await wait_until(lambda: call.bridge() is None, what="the bridge to unregister")
