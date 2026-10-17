"""SMS opt-outs (US carrier / 10DLC rules): STOP / START / HELP replies, the opt-out list,
skipped texts, and "Reply STOP to opt out." on an account's first text to a number.
No Telnyx, no database."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.core.ratelimit import backends
from app.models import Message
from app.services import sms_service
from app.services.sms import inbound, optout, sending
from tests.finance_fakes import Factory, FakeSession
from tests.security_fakes import make_merchant

OURS, CUSTOMER = "+18723428160", "+16175550142"


@pytest.fixture(autouse=True)
def _isolated():
    backends.memory.reset()
    yield
    backends.memory.reset()


def sql(stmt) -> str:  # noqa: ANN001
    return str(stmt.compile(dialect=postgresql.dialect()))


# ------------------------------------------------------------------ keywords (pure)
@pytest.mark.parametrize("text", ["STOP", "stop", " Stop. ", "Stop all", "STOPALL", "unsubscribe", "Cancel", "END", "quit!"])
def test_stop_words(text):
    assert optout.action_of(text) == "stop"


@pytest.mark.parametrize("text,action", [("START", "start"), ("unstop", "start"), ("Yes", "start"), ("help", "help"), ("INFO?", "help")])
def test_start_and_help_words(text, action):
    assert optout.action_of(text) == action


@pytest.mark.parametrize("text", ["", "Please cancel my appointment on Tuesday", "stop calling", "Yes please", "ok", None])
def test_sentences_are_not_keywords(text):
    assert optout.action_of(text) == ""


def test_numbers_compare_in_one_format():
    assert optout.canonical("+1 (617) 555-0142") == optout.canonical("+1 617 555 0142") == CUSTOMER
    assert optout.canonical(None) == ""


# ------------------------------------------------------------------ notice + help text (pure)
def test_first_text_notice_stays_in_one_segment_when_it_can():
    body = "Bright Smile Dental: your appointment with Dr. Lee is confirmed for Tue, Oct 20 at 3 PM. Call +16175550100 to change."
    assert optout.with_notice(body) == f"{body} Reply STOP to opt out." and len(optout.with_notice(body)) <= 160
    assert optout.with_notice(optout.with_notice(body)) == optout.with_notice(body)  # never twice
    assert optout.with_notice("") == ""
    long = "Bright Smile Dental Studio of Cambridge: your appointment with Dr. Sarah Lee is confirmed for Tue, Oct 20 at 3 PM. Call +16175550100 to change."
    assert 160 - 23 < len(long) <= 160
    # Texting from its own number the customer can call back: the call line makes room.
    trimmed = optout.with_notice(long, may_drop_call_line=True)
    assert trimmed.endswith("at 3 PM. Reply STOP to opt out.") and len(trimmed) <= 160 and "Call +1" not in trimmed
    kept = optout.with_notice(long)
    assert "Call +16175550100 to change." in kept and kept.endswith(optout.NOTICE)


def test_help_reply_names_the_business_and_fits_one_segment():
    text = optout.help_text("Bright Smile Dental", "+16175550100")
    assert text.startswith("Bright Smile Dental:") and "Call +16175550100." in text and text.endswith("Reply STOP to opt out.")
    assert len(text) <= 160 and text.isascii()
    assert len(optout.help_text("A" * 300, "+16175550100")) <= 160
    assert optout.help_text("").startswith("Callisa:")


# ------------------------------------------------------------------ the list
async def test_opt_outs_are_upserted_per_sender_and_matched_by_sender_or_account():
    session = FakeSession()
    await optout.record(session, sender="(872) 342-8160", phone=CUSTOMER, merchant_id="m1", keyword="STOP")
    statement = sql(session.executed[0][0])
    assert "ON CONFLICT ON CONSTRAINT uq_sms_opt_outs_sender_phone DO UPDATE" in statement
    await optout.remove(session, sender=OURS, phone=CUSTOMER, merchant_id="m1")
    removed = sql(session.executed[1][0])
    assert removed.startswith("DELETE FROM sms_opt_outs") and "merchant_id" in removed and "sender_number" in removed
    found = FakeSession(scalar=["row1"])
    assert await optout.is_opted_out(found, sender=OURS, phone=CUSTOMER, merchant_id="m1")
    assert "sms_opt_outs.merchant_id" in sql(found.statements[0])
    assert not await optout.is_opted_out(FakeSession(), sender=OURS, phone=CUSTOMER)
    assert not await optout.is_opted_out(FakeSession(scalar=["row1"]), sender=OURS, phone="")


# ------------------------------------------------------------------ inbound replies
def telnyx_payload(text: str, sender: str = CUSTOMER) -> dict:
    return {"id": "m-1", "direction": "inbound", "text": text, "from": {"phone_number": sender, "carrier": "T-Mobile"},
            "to": [{"phone_number": OURS, "status": "webhook_delivered"}]}


def test_inbound_payload_is_parsed():
    assert inbound.parse(telnyx_payload("STOP")) == ("STOP", CUSTOMER, OURS)
    assert inbound.parse({"text": "hi", "from": "+1 617 555 0142", "to": OURS}) == ("hi", CUSTOMER, OURS)
    assert inbound.parse(None) == ("", "", "")


@pytest.fixture
def replies(monkeypatch):
    session = FakeSession()
    merchant = make_merchant(id="m1", business_name="Bright Smile Dental", support_phone="+16175550100")
    helped: list[tuple] = []

    async def merchant_for(db, ours, phone):  # noqa: ANN001, ANN202
        return merchant

    async def reply_help(found, phone, ours):  # noqa: ANN001, ANN202
        helped.append((found.id, phone, ours))
        return "sent"

    monkeypatch.setattr(inbound, "AsyncSessionLocal", Factory(session))
    monkeypatch.setattr(inbound, "_merchant_for", merchant_for)
    monkeypatch.setattr(inbound, "reply_help", reply_help)
    return session, helped


async def test_stop_start_and_help_replies(replies):
    session, helped = replies
    assert await inbound.handle(telnyx_payload("Stop")) == "stop"
    assert session.commits == 1 and sql(session.executed[0][0]).startswith("INSERT INTO sms_opt_outs")
    assert session.executed[0][0].compile().params["merchant_id"] == "m1"
    assert await inbound.handle(telnyx_payload("START")) == "start" and sql(session.executed[1][0]).startswith("DELETE")
    assert await inbound.handle(telnyx_payload("help")) == "help"
    await asyncio.gather(*list(inbound._pending))
    assert helped == [("m1", CUSTOMER, OURS)]
    assert await inbound.handle(telnyx_payload("Can I move my appointment?")) == "" and len(session.executed) == 2
    assert await inbound.handle(telnyx_payload("STOP", sender="")) == ""


async def test_help_is_answered_once_an_hour(monkeypatch):
    sent: list[tuple] = []

    async def send(merchant, to, body, *, kind, order_id=None):  # noqa: ANN001, ANN202
        sent.append((to, body, kind))
        return Message(status="sent")

    monkeypatch.setattr(sending, "send", send)
    merchant = make_merchant(id="m1", business_name="Bright Smile Dental", support_phone="+16175550100")
    assert await inbound.reply_help(merchant, CUSTOMER, OURS) == "sent"
    assert await inbound.reply_help(merchant, CUSTOMER, OURS) == ""
    [(to, body, kind)] = sent
    assert to == CUSTOMER and kind == "help" and body == optout.help_text("Bright Smile Dental", "+16175550100")


def test_the_profile_webhook_routes_replies_and_receipts(monkeypatch):
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "enforce_webhook_signatures", False)
    monkeypatch.setattr(settings, "telnyx_public_key", None)
    handled, receipts = [], []

    async def handle(payload):  # noqa: ANN001, ANN202
        handled.append(payload["text"])
        return "stop"

    async def apply_status(message_id, status, error="", *, provider_sid=""):  # noqa: ANN001, ANN202
        receipts.append((status, provider_sid))

    monkeypatch.setattr(inbound, "handle", handle)
    monkeypatch.setattr(sms_service, "apply_status", apply_status)
    client = TestClient(app)
    received = {"data": {"event_type": "message.received", "payload": telnyx_payload("STOP")}}
    assert client.post("/telnyx/sms-events", json=received).status_code == 204 and handled == ["STOP"]
    finalized = {"data": {"event_type": "message.finalized", "payload": {"id": "t-1", "to": [{"status": "delivered"}]}}}
    assert client.post("/telnyx/sms-events", json=finalized).status_code == 204 and receipts == [("delivered", "t-1")]


# ------------------------------------------------------------------ sending
@pytest.fixture
def telnyx_out(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def send_sms(*, to, text, webhook_url=None, from_number=None):  # noqa: ANN001, ANN202
        sent.append({"to": to, "text": text, "from": from_number})
        return f"sid{len(sent)}"

    monkeypatch.setattr(sending, "platform_ready", lambda: True)
    monkeypatch.setattr(sending.telnyx, "send_sms", send_sms)
    monkeypatch.setattr(sending.telnyx, "number_for", lambda merchant: OURS)
    return sent


def db(monkeypatch, *answers) -> FakeSession:
    """``answers``: opted out? (a row id or None), then texted before? (a row id or None)."""
    session = FakeSession(scalar=list(answers))
    monkeypatch.setattr(sending, "AsyncSessionLocal", Factory(session))
    return session


async def test_an_opted_out_number_is_skipped_with_the_reason(monkeypatch, telnyx_out):
    session = db(monkeypatch, "optout-1")
    message = await sending.send(make_merchant(), CUSTOMER, "Your booking is confirmed.", kind="confirmation")
    assert message.status == "skipped" and message.error == optout.OPTED_OUT and not telnyx_out
    assert session.rows[(Message, message.id)].error == optout.OPTED_OUT  # "Recent texts" shows why
    db(monkeypatch, "optout-2")  # the owner's own STOP is respected too
    alert = await sending.send(make_merchant(), "+16175550199", "Callisa: New booking", kind=sending.KIND_ALERT)
    assert alert.status == "skipped" and not telnyx_out


async def test_first_text_to_a_number_carries_the_stop_notice_and_later_ones_dont(monkeypatch, telnyx_out):
    db(monkeypatch, None, None)
    first = await sending.send(make_merchant(), CUSTOMER, "Demo Shop: your order is confirmed.", kind="confirmation")
    assert first.status == "sent" and telnyx_out[0]["text"] == "Demo Shop: your order is confirmed. Reply STOP to opt out."
    assert first.body.endswith(optout.NOTICE) and telnyx_out[0]["from"] == OURS
    db(monkeypatch, None, "msg-earlier")
    later = await sending.send(make_merchant(), CUSTOMER, "Demo Shop: your order has shipped.", kind="change")
    assert telnyx_out[1]["text"] == "Demo Shop: your order has shipped." and later.status == "sent"


async def test_help_replies_skip_the_list_and_the_notice(monkeypatch, telnyx_out):
    session = db(monkeypatch)
    body = optout.help_text("Demo Shop")
    message = await sending.send(make_merchant(), CUSTOMER, body, kind=sending.KIND_HELP)
    assert message.status == "sent" and telnyx_out[0]["text"] == body and not session.statements


async def test_owner_alerts_are_not_bound_by_the_per_number_cap(monkeypatch, telnyx_out):
    monkeypatch.setattr(get_settings(), "sms_daily_cap_per_number", 1)
    db(monkeypatch)
    statuses = [(await sending.send(make_merchant(), "+16175550199", "Callisa: New booking", kind=sending.KIND_ALERT)).status for _ in range(3)]
    assert statuses == ["sent", "sent", "sent"]
    db(monkeypatch)
    capped = [(await sending.send(make_merchant(), CUSTOMER, "Hi", kind="confirmation")).status for _ in range(2)]
    assert capped == ["sent", "skipped"]


@pytest.mark.parametrize(
    "vertical,kind,item,details",
    [
        ("clinic", "appointment", "Dr. James Carter", {}),
        ("salon", "booking", "Maya", {"service": "Haircut"}),
        ("restaurant", "booking", "", {"party_size": 4}),
        ("custom", "booking", "Consultation", {}),
        ("vet", "appointment", "Dr. Lee", {"pet_name": "Bella"}),
        ("ecommerce", "order", "", {}),
    ],
)
def test_confirmations_with_the_stop_notice_fit_one_segment(vertical, kind, item, details):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    merchant = SimpleNamespace(business_name="CityCare Partners", language="en", support_phone="+16175550100", phone="", vertical=vertical,
                               timezone="America/New_York", region="US", currency="USD", vertical_config={})
    record = SimpleNamespace(kind=kind, scheduled_at=datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc), items_summary=item, address="",
                             total_amount=45, currency="USD", order_ref="UT-1001", details=details)
    text = optout.with_notice(sms_service.compose("confirmation", record, merchant, item_name=item))
    assert text.endswith("Reply STOP to opt out.") and text.isascii() and sms_service.segments(text) == 1, (len(text), text)
