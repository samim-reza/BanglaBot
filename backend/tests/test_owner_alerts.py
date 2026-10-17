"""Owner alerts: settings and defaults, outcome → event, the wording (email + text), the
background delivery (once per outcome, waits briefly for the summary) and the API.
No SMTP, no Telnyx, no database."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.ratelimit import backends
from app.models import CallLog, Order, OrderStatus
from app.services import alerts, notification_service
from app.services.alerts import compose, dispatch
from app.services.summaries import runner
from tests.finance_fakes import Factory, FakeSession
from tests.security_fakes import FakeDB, db_override, make_merchant

PORTAL = "https://app.callisa.test"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    backends.memory.reset()
    runner._done.clear()
    runner._events.clear()
    monkeypatch.setattr(get_settings(), "frontend_origin", PORTAL)
    yield
    monkeypatch.setattr(dispatch, "session_factory", None)
    backends.memory.reset()


@pytest.fixture
def outbox(monkeypatch) -> dict[str, list]:
    """SMTP + SMS switched on, both captured."""
    sent: dict[str, list] = {"email": [], "sms": []}

    def smtp_send(*, to, subject, body):  # noqa: ANN001, ANN202
        sent["email"].append({"to": to, "subject": subject, "body": body})

    async def sms_send(merchant, to, body, *, kind, order_id=None):  # noqa: ANN001, ANN202
        sent["sms"].append({"to": to, "body": body, "kind": kind})
        return SimpleNamespace(status="sent", error="")

    from app.core import email
    from app.services.sms import sending

    monkeypatch.setattr(email, "send_email", smtp_send)
    monkeypatch.setattr(sending, "send", sms_send)
    monkeypatch.setattr(dispatch, "smtp_ready", lambda: True)
    monkeypatch.setattr(dispatch, "sms_ready", lambda: True)
    return sent


def account(**alert_settings):
    return make_merchant(id="m1", business_name="Bright Smile Dental", email="owner@brightsmile.test", alert_settings=alert_settings)


def booking(**overrides) -> Order:
    values = dict(
        id="o1", merchant_id="m1", kind="appointment", customer_name="Emily Johnson", customer_phone="+16175550142",
        items_summary="Cleaning", total_amount=Decimal("120"), currency="USD", order_ref="BS-1001", status=OrderStatus.confirmed,
        scheduled_at=datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return Order(**values)


def stored(monkeypatch, merchant, *rows) -> FakeSession:
    session = FakeSession(merchant, *rows)
    monkeypatch.setattr(dispatch, "session_factory", Factory(session))
    return session


# ------------------------------------------------------------------ settings (pure)
def test_defaults_email_bookings_messages_and_urgent_never_sms():
    merchant = account()
    assert alerts.settings_of(merchant) == {"email_events": ["booking", "message", "urgent"], "sms_events": [], "sms_to": ""}
    assert alerts.channels_for(merchant, "booking") == ["email"] and alerts.channels_for(merchant, "change") == []
    no_email = make_merchant(email="not-an-email", alert_settings={})
    assert alerts.email_to(no_email) == "" and alerts.channels_for(no_email, "urgent") == []
    custom = account(email_events=["urgent", "bogus"], sms_events=["change", "booking"], sms_to=" +16175550199 ")
    assert alerts.settings_of(custom) == {"email_events": ["urgent"], "sms_events": ["booking", "change"], "sms_to": "+16175550199"}
    assert alerts.channels_for(custom, "booking") == ["sms"] and alerts.channels_for(custom, "urgent") == ["email"]
    assert alerts.channels_for(custom, "nonsense") == []


def test_which_outcomes_alert():
    assert alerts.event_for("booked") == "booking" and alerts.event_for("rescheduled") == "change"
    assert alerts.event_for("cancelled") == alerts.event_for("not_interested") == "change"
    assert alerts.event_for("lead") == alerts.event_for("relay") == "message"
    assert alerts.event_for("emergency") == alerts.event_for("transfer") == alerts.event_for("unclear") == "urgent"
    assert alerts.event_for("confirmed", "order") == "booking" and alerts.event_for("confirmed", "appointment") == ""
    assert alerts.event_for("inquiry") == alerts.event_for("no_answer") == alerts.event_for("") == ""


# ------------------------------------------------------------------ wording (pure)
def test_email_is_short_scannable_and_links_the_record():
    log = CallLog(id="c1", merchant_id="m1", direction="inbound", caller_number="+16175550142")
    alert = compose.build(account(), event="booking", outcome="booked", record=booking(), log=log, summary="Emily booked a cleaning.")
    subject, body = compose.email(alert)
    assert subject == "New appointment: Emily Johnson, Tue, Oct 20 at 3 PM"
    assert "Emily Johnson +16175550142" in body and "Cleaning · Tue, Oct 20 at 3 PM · $120 · Ref BS-1001" in body
    assert "Emily booked a cleaning." in body and "Phone call" in body
    assert f"Open: {PORTAL}/orders/o1" in body and f"{PORTAL}/settings?tab=notifications" in body
    urgent = compose.build(account(), event="urgent", outcome="emergency", log=log)
    assert compose.email(urgent)[0].startswith("Urgent - Emergency: +16175550142") and urgent.link == f"{PORTAL}/calls"
    assert compose.title_for("booking", "confirmed", "order") == "Order confirmed"
    assert compose.title_for("message", "lead", "message") == "New message" and compose.title_for("urgent", "transfer") == "Wants a person"


def test_owner_text_is_ascii_and_drops_the_summary_when_too_long():
    alert = compose.build(account(), event="booking", outcome="booked", record=booking(customer_name="Zoë – Smith"), summary="Zoë booked “a cleaning”.")
    text = compose.sms(alert)
    assert text.isascii() and text.startswith("Callisa: New appointment - Zoe - Smith +16175550142. Cleaning, Tue, Oct 20 at 3 PM, $120")
    assert '"a cleaning"' in text and text.endswith(f"{PORTAL}/orders/o1") and len(text) <= compose.SMS_MAX_CHARS
    wordy = compose.build(account(), event="booking", outcome="booked", record=booking(), summary="word " * 80)
    assert "word" not in compose.sms(wordy) and compose.sms(wordy).endswith("/orders/o1")
    message = compose.build(account(), event="message", outcome="lead", record=booking(kind="message", items_summary="Please call me " * 20, customer_phone="6175550142"))
    assert len(message.what) <= compose.WHAT_MAX_CHARS and message.what.endswith("...") and message.phone == "+16175550142"
    assert message.title == "New message"
    chat = compose.build(account(), event="message", outcome="lead", log=CallLog(id="c2", merchant_id="m1", direction="widget"))
    assert compose.sms(chat).startswith("Callisa: New lead - Website visitor.")


# ------------------------------------------------------------------ delivery
async def test_an_outcome_alerts_once_with_the_summary_it_waited_for(monkeypatch, outbox):
    merchant = account(sms_events=["booking"], sms_to="+16175550199")
    log = CallLog(id="c1", merchant_id="m1", direction="inbound", caller_number="+16175550142", order_id="o1")
    stored(monkeypatch, merchant, booking(), log)
    task = asyncio.create_task(alerts.deliver("m1", "o1", "booked", call_log_id="c1"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not outbox["email"]  # waiting for the call to end and its summary
    runner._signal("c1", "Emily Johnson booked a cleaning for Tuesday.")
    assert await task == {"email": "sent", "sms": "sent"}
    [mail], [text] = outbox["email"], outbox["sms"]
    assert mail["to"] == "owner@brightsmile.test" and "Emily Johnson booked a cleaning for Tuesday." in mail["body"]
    assert text["to"] == "+16175550199" and text["kind"] == "alert" and "booked a cleaning" in text["body"]
    # The same outcome written again in that call (e.g. details re-saved): no second alert.
    assert await alerts.deliver("m1", "o1", "booked", call_log_id="c1") == {}
    assert len(outbox["email"]) == 1


async def test_no_summary_in_time_sends_without_it(monkeypatch, outbox):
    monkeypatch.setattr(dispatch, "URGENT_SUMMARY_WAIT_SECONDS", 0.01)
    log = CallLog(id="c3", merchant_id="m1", direction="inbound", caller_number="+16175550142")
    stored(monkeypatch, account(), log)
    assert await alerts.deliver("m1", "", "emergency", call_log_id="c3") == {"email": "sent"}
    assert outbox["email"][0]["subject"].startswith("Urgent - Emergency") and "Open: " in outbox["email"][0]["body"]
    written = CallLog(id="c4", merchant_id="m1", direction="inbound", summary="Already summarized.")
    stored(monkeypatch, account(), written)
    await alerts.deliver("m1", "", "transfer", call_log_id="c4")
    assert "Already summarized." in outbox["email"][-1]["body"]


async def test_nothing_is_sent_without_a_ready_channel_or_for_quiet_outcomes(monkeypatch, outbox):
    stored(monkeypatch, account(), booking())
    assert await alerts.deliver("m1", "o1", "inquiry", call_log_id="c1") == {}
    assert await alerts.deliver("m1", "o1", "rescheduled", call_log_id="c1") == {}  # changes are off by default
    monkeypatch.setattr(dispatch, "smtp_ready", lambda: False)
    assert await alerts.deliver("m1", "o1", "booked", call_log_id="c1") == {}
    assert await alerts.deliver("missing", "o1", "booked", call_log_id="c1") == {}
    assert outbox == {"email": [], "sms": []}


async def test_a_broken_database_never_raises(monkeypatch):
    class Broken:
        def __call__(self):
            raise ConnectionError("database unreachable")

    monkeypatch.setattr(dispatch, "session_factory", Broken())
    assert await alerts.deliver("m1", "o1", "booked", call_log_id="c1") == {}


async def test_agent_outcomes_schedule_the_alert_with_or_without_a_record(monkeypatch):
    seen: list[tuple] = []

    async def deliver(merchant_id, record_id, outcome, *, call_log_id=""):  # noqa: ANN001, ANN202
        seen.append((merchant_id, record_id, outcome, call_log_id))
        return {}

    async def customer_text(*args):  # noqa: ANN002, ANN202
        return None

    monkeypatch.setattr(dispatch, "deliver", deliver)
    monkeypatch.setattr(notification_service, "_after_outcome", customer_text)
    notification_service.after_outcome("m1", "", "emergency", call_log_id="c1")
    notification_service.after_outcome("m1", "o1", "inquiry", call_log_id="c2")  # never alerts
    notification_service.after_outcome("m1", "o1", "booked")  # a portal change: no alert
    await asyncio.gather(*list(dispatch._pending))
    assert seen == [("m1", "", "emergency", "c1")]


async def test_test_alert_goes_to_every_recipient(outbox, monkeypatch):
    results = await alerts.send_test(account(sms_to="+16175550199"))
    assert results["email"] == {"status": "sent", "detail": "Sent to owner@brightsmile.test."}
    assert results["sms"]["status"] == "sent" and "Test alert" in outbox["sms"][0]["body"]
    monkeypatch.setattr(dispatch, "smtp_ready", lambda: False)
    assert (await alerts.send_test(account()))["email"]["status"] == "skipped"


# ------------------------------------------------------------------ API
@pytest.fixture
def portal(monkeypatch):
    from app.api.deps import get_current_merchant
    from app.db.session import get_db
    from app.main import app

    merchant = account()
    app.dependency_overrides[get_current_merchant] = lambda: merchant
    app.dependency_overrides[get_db] = db_override(FakeDB())
    try:
        yield TestClient(app), merchant
    finally:
        app.dependency_overrides.pop(get_current_merchant, None)
        app.dependency_overrides.pop(get_db, None)


def test_settings_save_validate_and_come_back_in_the_summary(portal):
    client, merchant = portal
    saved = client.patch("/api/integrations/alerts", json={"sms_events": ["urgent", "booking"], "sms_to": "(617) 555-0199"})
    assert saved.status_code == 200, saved.text
    body = saved.json()["alerts"]
    assert body["settings"] == {"email_events": ["booking", "message", "urgent"], "sms_events": ["booking", "urgent"], "sms_to": "+16175550199"}
    assert body["email_to"] == "owner@brightsmile.test" and set(body) >= {"email_ready", "sms_ready"}
    assert merchant.alert_settings["sms_to"] == "+16175550199"
    assert client.patch("/api/integrations/alerts", json={"sms_to": ""}).status_code == 422  # texts on, nowhere to send
    assert client.patch("/api/integrations/alerts", json={"sms_to": "12"}).status_code == 422
    assert client.patch("/api/integrations/alerts", json={"email_events": ["everything"]}).status_code == 422
    off = client.patch("/api/integrations/alerts", json={"sms_events": [], "email_events": []}).json()["alerts"]["settings"]
    assert off["sms_events"] == [] and off["email_events"] == []


def test_test_alert_endpoint_is_rate_limited(portal, outbox):
    client, merchant = portal
    for _ in range(dispatch_limit()):
        response = client.post("/api/integrations/alerts/test")
        assert response.status_code == 200 and response.json()["results"]["email"]["status"] == "sent"
    assert client.post("/api/integrations/alerts/test").status_code == 429
    backends.memory.reset()
    merchant.email = ""
    assert client.post("/api/integrations/alerts/test").status_code == 422


def dispatch_limit() -> int:
    from app.api.routes.integrations import alerts as routes

    return routes.TEST_ALERTS_PER_WINDOW
