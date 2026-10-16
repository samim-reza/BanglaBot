"""Outbound calls with a fake Telnyx API: the owner presses "Call", the TeXML the call was
created with streams to the media socket, the callee answers, the outcome lands on the
record, and the carrier's AMD / status / recording callbacks settle it."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest

from tests.e2e.api import admin_token, create_account, fetch, ok
from tests.e2e.fakes import text_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import PhoneCall, booking_day
from tests.e2e.telnyx_peer import TelnyxMediaPeer, parse_stream, wait_until


@dataclass
class FakeTelnyx:
    calls: list[dict] = field(default_factory=list)
    hangups: list[str] = field(default_factory=list)

    async def create_call(self, **kwargs) -> str:  # noqa: ANN003
        self.calls.append(kwargs)
        return f"v3:e2e-out-{len(self.calls)}"

    async def hangup_call(self, call_sid: str) -> None:
        self.hangups.append(call_sid)


@pytest.fixture
def telnyx_api(monkeypatch) -> FakeTelnyx:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services import telnyx

    fake = FakeTelnyx()
    settings = get_settings()
    for name, value in (("telnyx_api_key", "KEY-e2e"), ("telnyx_texml_app_id", "app-e2e"), ("telnyx_from_number", "+18725550000")):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(telnyx, "create_call", fake.create_call)
    monkeypatch.setattr(telnyx, "hangup_call", fake.hangup_call)

    async def no_recording(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
        return None

    monkeypatch.setattr(telnyx, "start_recording", no_recording)
    return fake


async def _answer(app, providers, fake: FakeTelnyx, customer: str) -> PhoneCall:  # noqa: ANN001
    created = fake.calls[-1]
    assert created["to"] == customer and created["from_number"]
    answer = parse_stream(created["texml"])
    sessions = len(providers.stts)
    peer = TelnyxMediaPeer(app, answer.url)
    await peer.open()
    sid = f"v3:e2e-out-{len(fake.calls)}"
    await peer.start(answer.parameters, call_control_id=sid, caller="+18725550000", called=customer)
    await wait_until(lambda: len(providers.stts) > sessions, what="the STT session")
    call = PhoneCall(peer=peer, answer=answer, stt=providers.stts[-1], call_sid=sid)
    await wait_until(lambda: len(call.agent_lines()) >= 1, what="the opening")
    return call


async def test_clinic_reminder_call_confirms_attendance_and_callbacks_settle_it(app, client, providers, telnyx_api):
    from app.models import CallLog, Order
    from app.services import telnyx_urls

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="clinic", plan="growth")
    headers = account["headers"]
    doctor = await ok(await client.post("/api/catalog", headers=headers, json={
        "name": "Dr. Rao", "specialty": "Medicine", "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "start_time": "09:00", "end_time": "17:00",
    }), 201)
    customer = "+14155551201"
    record = await ok(await client.post("/api/orders", headers=headers, json={
        "customer_name": "Ravi Kumar", "customer_phone": customer, "catalog_item_id": doctor["id"], "scheduled_at": f"{booking_day(2)}T11:00",
    }), 201)

    providers.script(text_reply("Sorry, could you say that again?"))
    calling = await ok(await client.post(f"/api/orders/{record['id']}/call", headers=headers))
    assert calling["status"] == "calling" and calling["call_attempts"] == 1
    assert telnyx_api.calls[-1]["status_callback"].startswith("http://testserver/telnyx/status/")
    # A human answered (AMD), the stream connects, the agent opens with the reminder.
    amd_path = urlsplit(telnyx_api.calls[-1]["amd_callback"]).path
    assert (await client.post(amd_path, data={"CallSid": "v3:e2e-out-1", "AnsweredBy": "human"})).status_code == 204
    call = await _answer(app, providers, telnyx_api, customer)
    assert call.agent_lines()[0].endswith("Am I speaking with Ravi Kumar?"), call.agent_lines()
    await call.says("Yes, speaking.")
    assert "appointment with Dr. Rao" in call.agent_lines()[-1], call.agent_lines()
    await call.says("Yes, I'll be there.")
    await call.wraps_up()
    await settle_background()

    [row] = await fetch(Order, id=record["id"])
    [log] = await fetch(CallLog, order_id=record["id"])
    assert row.status.value == "confirmed", (row.status, log.outcome, row.notes, log.transcript)
    assert log.direction == "outbound" and log.outcome and "Customer: Yes, I'll be there." in log.transcript
    assert telnyx_api.hangups == ["v3:e2e-out-1"]  # the agent ended the phone leg
    # The carrier's final status and the recording arrive after the hangup.
    status_path = urlsplit(telnyx_urls.status_callback_url(record["id"])).path
    response = await client.post(status_path, data={"CallSid": "v3:e2e-out-1", "CallStatus": "completed", "CallDuration": "37"})
    assert response.status_code == 204
    recording_path = urlsplit(telnyx_urls.recording_callback_url(record["id"])).path
    assert (await client.post(recording_path, data={"CallSid": "v3:e2e-out-1", "RecordingSid": "rec-out-1"})).status_code == 204
    [log] = await fetch(CallLog, id=log.id)
    assert log.call_status == "completed" and log.duration_secs == 37 and log.recording_sid == "rec-out-1"
    [row] = await fetch(Order, id=record["id"])
    assert row.status.value == "confirmed"  # the status callback never undoes the agent's outcome


async def test_voicemail_is_hung_up_and_the_record_stays_callable(client, providers, telnyx_api):
    from app.models import CallLog, Order
    from app.services import telnyx_urls

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="ecommerce", plan="growth")
    headers = account["headers"]
    record = await ok(await client.post("/api/orders", headers=headers, json={
        "customer_name": "Vee Mail", "customer_phone": "+14155551202", "items_summary": "Blue kurta x1", "total_amount": "30",
        "address": "1 Main St, Springfield",
    }), 201)
    providers.script(text_reply("You ordered one blue kurta, 30 dollars. Shall I confirm the order?"))
    await ok(await client.post(f"/api/orders/{record['id']}/call", headers=headers))
    amd_path = urlsplit(telnyx_api.calls[-1]["amd_callback"]).path
    assert (await client.post(amd_path, data={"CallSid": "v3:e2e-out-1", "AnsweredBy": "machine_end_beep"})).status_code == 204
    assert telnyx_api.hangups == ["v3:e2e-out-1"]
    status_path = urlsplit(telnyx_urls.status_callback_url(record["id"])).path
    await client.post(status_path, data={"CallSid": "v3:e2e-out-1", "CallStatus": "completed", "CallDuration": "9"})
    await settle_background()
    [row] = await fetch(Order, id=record["id"])
    assert row.status.value == "no_answer", row.status
    [log] = await fetch(CallLog, order_id=record["id"])
    assert log.outcome == "voicemail" and log.call_status == "completed"
    # It can be called again.
    again = await client.post(f"/api/orders/{record['id']}/call", headers=headers)
    assert again.status_code == 200 and again.json()["call_attempts"] == 2


async def test_ecommerce_order_confirmation_call(app, client, providers, telnyx_api, sms_outbox):
    from app.models import CallLog, Message, Order
    from app.voice import prepared

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="ecommerce", plan="growth")
    headers = account["headers"]
    await ok(await client.patch("/api/integrations/sms", json={"enabled": True}, headers=headers))
    customer = "+14155551203"
    record = await ok(await client.post("/api/orders", headers=headers, json={
        "customer_name": "Rahim Uddin", "customer_phone": customer, "items_summary": "Cotton kurta (L) x1", "total_amount": "45",
        "address": "12 Oak Street, Springfield", "order_ref": "A-1001",
    }), 201)
    # While the phone rings, the model composes the confirmation question (cached for the first turn).
    decision = "You ordered one cotton kurta, size large, 45 dollars, to 12 Oak Street. Shall I confirm the order?"
    providers.script(text_reply(decision))
    await ok(await client.post(f"/api/orders/{record['id']}/call", headers=headers))
    await wait_until(lambda: prepared.get_decision_line(record["id"], "en"), what="the prepared decision line")
    call = await _answer(app, providers, telnyx_api, customer)
    await call.says("Yes, speaking.")
    assert call.agent_lines()[-1] == decision, call.agent_lines()
    await call.says("Yes, please confirm it.")
    await call.wraps_up()
    await settle_background()
    [row] = await fetch(Order, id=record["id"])
    [log] = await fetch(CallLog, order_id=record["id"])
    assert row.status.value == "confirmed" and log.outcome == "confirmed", (row.status, log.transcript)
    [text] = [m for m in sms_outbox if m["to"] == customer]
    assert "order A-1001" in text["text"] and "confirmed" in text["text"], text
    assert [m.kind for m in await fetch(Message, merchant_id=account["merchant"]["id"])] == ["confirmation"]
