"""SMS confirmations and calendar sync — composed, parsed and mocked at the HTTP layer
(no Twilio, no Google, no database)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.core import memo
from app.core.crypto import decrypt, encrypt
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import Window, free_slots
from app.flows.timefmt import business_tz
from app.models import CatalogItem, Order, OrderStatus
from app.services import calendar_service, sms_service
from app.services.ics import FeedEvent, build_calendar, busy_intervals

NY = business_tz("America/New_York")


# ------------------------------------------------------------------------------ crypto
def test_secrets_round_trip_and_never_leak_plaintext():
    token = encrypt("1//refresh-token")
    assert token and "refresh" not in token and decrypt(token) == "1//refresh-token"
    assert decrypt("garbage") == "" and encrypt("") == ""


# ------------------------------------------------------------------------------ iCal
ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20261005T120000
DTEND;TZID=America/New_York:20261005T130000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4
EXDATE;TZID=America/New_York:20261007T120000
SUMMARY:Lunch
BEGIN:VALARM
TRIGGER:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261009
DTEND;VALUE=DATE:20261010
SUMMARY:Conference (all day)
END:VEVENT
BEGIN:VEVENT
DTSTART:20261006T140000Z
DURATION:PT30M
TRANSP:TRANSPARENT
SUMMARY:Free time
END:VEVENT
BEGIN:VEVENT
DTSTART:20261008T140000Z
DTEND:20261008T150000Z
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR"""


def test_ical_busy_times_expand_recurrences_and_skip_free_or_cancelled():
    busy = busy_intervals(ICS, window_start=datetime(2026, 10, 1, tzinfo=NY), window_end=datetime(2026, 10, 31, tzinfo=NY), timezone_name="America/New_York")
    assert [(s.strftime("%m-%d %H:%M"), e.strftime("%m-%d %H:%M")) for s, e in busy] == [
        ("10-05 12:00", "10-05 13:00"),
        ("10-09 00:00", "10-10 00:00"),  # all day
        ("10-12 12:00", "10-12 13:00"),  # Wed the 7th was an EXDATE
        ("10-14 12:00", "10-14 13:00"),  # COUNT=4 includes the excluded one
    ]


def test_feed_is_valid_ical_with_escaping_and_folding():
    text = build_calendar(
        "CityCare, Boston",
        [FeedEvent("rec-1@x", datetime(2026, 10, 5, 14, tzinfo=timezone.utc), datetime(2026, 10, 5, 15, tzinfo=timezone.utc), "Leo; Carter", "Phone: +1\n" * 20)],
    )
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "X-WR-CALNAME:CityCare\\, Boston" in text and "SUMMARY:Leo\\; Carter" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    # Our own feed parses back.
    busy = busy_intervals(text, window_start=datetime(2026, 10, 1, tzinfo=timezone.utc), window_end=datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert busy == [(datetime(2026, 10, 5, 14, tzinfo=timezone.utc), datetime(2026, 10, 5, 15, tzinfo=timezone.utc))]


def test_busy_times_block_overlapping_slots():
    from datetime import date, time

    window = Window(start=time(9, 0), end=time(11, 0), step_minutes=30)
    now = datetime(2026, 10, 5, 6, 0, tzinfo=NY)
    busy = [(datetime(2026, 10, 5, 9, 45, tzinfo=NY), datetime(2026, 10, 5, 10, 15, tzinfo=NY))]
    slots = free_slots([window], date(2026, 10, 5), now=now, busy=busy)
    assert [s.start.strftime("%H:%M") for s in slots] == ["09:00", "10:30"]


@pytest.mark.asyncio
async def test_clinic_never_offers_a_time_the_doctor_is_busy():
    from app.flows.runtime import FlowRuntime
    from app.verticals import flow_for
    from app.voice.tools import CallTools, NullCallStore

    merchant = SimpleNamespace(vertical="clinic", business_name="CityCare", language="en", region="US", timezone="America/New_York",
                               currency="USD", emergency_number="911", custom_greeting="", support_phone="", knowledge="", vertical_config={}, sms_settings={})
    doctor = CatalogEntry("d1", "D1", "doctor", "Dr. Nair", {"specialty": "Dermatology", "days": ["tue"], "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30})
    ctx = CallContext(
        merchant=merchant, catalog=[doctor], direction=DIRECTION_INBOUND, caller_number="+16175550100",
        now=datetime(2026, 10, 2, 20, 0, tzinfo=NY),
        busy={"d1": [(datetime(2026, 10, 6, 9, 0, tzinfo=NY), datetime(2026, 10, 6, 10, 0, tzinfo=NY))]},
    )
    tools = CallTools(FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en"), NullCallStore())
    result = await tools.execute("save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-06", "patient_name": "Ann"}, caller_text="Tuesday please, Ann")
    assert "10 AM" in result.say  # 9:00 and 9:30 are in the doctor's busy block


# ------------------------------------------------------------------------------ SMS
def _merchant(**kw):
    base = dict(business_name="CityCare", language="en", support_phone="+16175550100", phone="", timezone="America/New_York",
                region="US", currency="USD", vertical_config={}, sms_settings={"enabled": True})
    base.update(kw)
    return SimpleNamespace(**base)


def test_sms_texts_per_event_stay_in_one_or_two_gsm_segments():
    record = SimpleNamespace(kind="appointment", scheduled_at=datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc), items_summary="", address="",
                             total_amount=140, currency="USD", order_ref="", details={})
    for kind in ("confirmation", "change", "cancellation", "reminder"):
        text = sms_service.compose(kind, record, _merchant(), item_name="Dr. James Carter")
        assert "Wed, Oct 7 at 10 AM" in text and sms_service.segments(text) == 1 and text.isascii()
    booking = SimpleNamespace(kind="booking", scheduled_at=datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc), items_summary="Electrical",
                              address="77 Court St", total_amount=85, currency="USD", order_ref="", details={"time_window": "afternoon"})
    text = sms_service.compose("confirmation", booking, _merchant(business_name="FixRight"))
    assert "Mon, Oct 5, 12 PM-3 PM at 77 Court St" in text and "$85" in text and text.isascii()
    assert sms_service.segments("x" * 160) == 1 and sms_service.segments("x" * 161) == 2 and sms_service.segments("অ" * 71) == 2


def test_which_outcomes_send_a_text(monkeypatch):
    monkeypatch.setattr(sms_service, "platform_ready", lambda: True)
    merchant = _merchant()
    assert sms_service.planned_kind(merchant, "booked", record_kind="appointment", phone="+1") == "confirmation"
    assert sms_service.planned_kind(merchant, "rescheduled", record_kind="appointment", phone="+1") == "change"
    assert sms_service.planned_kind(merchant, "confirmed", record_kind="appointment", phone="+1") is None  # reminder call "yes"
    assert sms_service.planned_kind(merchant, "confirmed", record_kind="order", phone="+1") == "confirmation"
    assert sms_service.planned_kind(merchant, "booked", record_kind="appointment", phone="") is None
    assert sms_service.planned_kind(_merchant(sms_settings={"enabled": False}), "booked", phone="+1") is None
    assert sms_service.planned_kind(_merchant(sms_settings={"enabled": True, "on_change": False}), "cancelled", phone="+1") is None
    monkeypatch.setattr(sms_service, "platform_ready", lambda: False)
    assert sms_service.planned_kind(merchant, "booked", phone="+1") is None


@pytest.mark.asyncio
async def test_the_agent_says_a_text_is_coming(monkeypatch):
    from app.flows.runtime import FlowRuntime
    from app.verticals import flow_for
    from app.voice.tools import CallTools, NullCallStore

    monkeypatch.setattr(sms_service, "platform_ready", lambda: True)
    merchant = SimpleNamespace(vertical="home_service", business_name="FixRight", language="en", region="US", timezone="America/New_York",
                               currency="USD", emergency_number="911", custom_greeting="", support_phone="", knowledge="",
                               vertical_config={"teams": 2}, sms_settings={"enabled": True})
    service = CatalogEntry("s1", "S1", "service", "AC repair", {"visit_charge": 89})
    ctx = CallContext(merchant=merchant, catalog=[service], direction=DIRECTION_INBOUND, caller_number="+17185550101", now=datetime(2026, 10, 2, 20, 0, tzinfo=NY))
    tools = CallTools(FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en"), NullCallStore())
    await tools.execute("save_details", {"service": "S1", "problem": "leak", "customer_name": "Mark", "address": "1 Main St", "date": "2026-10-05"}, caller_text="AC leak, Mark, 1 Main St, Monday")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "booked"
    assert "We'll text you the details. Thank you, goodbye." in result.say


# ------------------------------------------------------------------------------ Google (mocked)
class Google:
    """A tiny fake of the Google token + Calendar endpoints."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.created: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.url.host == "oauth2.googleapis.com" and request.url.path == "/token":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form.get("grant_type") == "authorization_code":
                claims = "eyJhbGciOiJub25lIn0." + __import__("base64").urlsafe_b64encode(json.dumps({"email": "dr@clinic.example"}).encode()).decode().rstrip("=") + "."
                return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600, "id_token": claims})
            return httpx.Response(200, json={"access_token": "at-2", "expires_in": 3600})
        if request.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary@x", "summary": "Clinic", "primary": True}, {"id": "nair@x", "summary": "Dr. Nair"}]})
        if request.url.path.endswith("/events") and request.method == "GET":
            assert request.headers["authorization"] == "Bearer at-2"
            return httpx.Response(200, json={"items": [
                {"start": {"dateTime": "2026-10-06T09:00:00-04:00"}, "end": {"dateTime": "2026-10-06T10:00:00-04:00"}},
                {"start": {"dateTime": "2026-10-06T11:00:00-04:00"}, "end": {"dateTime": "2026-10-06T12:00:00-04:00"}, "transparency": "transparent"},
                {"start": {"dateTime": "2026-10-06T13:00:00-04:00"}, "end": {"dateTime": "2026-10-06T14:00:00-04:00"},
                 "extendedProperties": {"private": {calendar_service.EVENT_TAG: "rec-9"}}},
                {"start": {"date": "2026-10-08"}, "end": {"date": "2026-10-09"}},
            ]})
        if request.url.path.endswith("/events") and request.method == "POST":
            self.created.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "evt-1"})
        return httpx.Response(404)


@pytest.fixture
def google(monkeypatch):
    from app.core.config import get_settings

    fake = Google()
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(calendar_service, "http", lambda: client)
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    memo.clear()
    yield fake
    memo.clear()


@pytest.mark.asyncio
async def test_google_connect_then_read_busy_times_skipping_our_own_events(google):
    url = calendar_service.auth_url("m1")
    assert "access_type=offline" in url and "calendar" in url and calendar_service.merchant_from_state(url.split("state=")[1]) == "m1"
    connected = await calendar_service.exchange_code("code-1")
    assert connected["email"] == "dr@clinic.example" and decrypt(connected["refresh_token_enc"]) == "rt-1"
    merchant = SimpleNamespace(id="m1", timezone="America/New_York", region="US", calendar_settings={"google": {"refresh_token_enc": connected["refresh_token_enc"]}})
    busy = await calendar_service.google_busy(merchant, "primary", window_start=datetime(2026, 10, 5, tzinfo=NY), window_end=datetime(2026, 10, 10, tzinfo=NY))
    assert [(s.strftime("%m-%d %H:%M"), e.strftime("%m-%d %H:%M")) for s, e in busy] == [("10-06 09:00", "10-06 10:00"), ("10-08 00:00", "10-09 00:00")]
    calendars = await calendar_service.list_calendars(merchant)
    assert [c["name"] for c in calendars] == ["Clinic", "Dr. Nair"]
    # The access token was refreshed once and reused.
    assert sum(1 for method, path in google.calls if path == "/token") == 2


def test_google_event_carries_our_tag_and_the_account_time_zone():
    merchant = SimpleNamespace(vertical="clinic", timezone="America/New_York", region="US", vertical_config={})
    item = CatalogItem(id="d1", merchant_id="m1", kind="doctor", name="Dr. Nair", data={"slot_minutes": 15})
    record = Order(id="rec-1", merchant_id="m1", kind="appointment", customer_name="Ann", customer_phone="+1", address="", notes="",
                   status=OrderStatus.confirmed, scheduled_at=datetime(2026, 10, 6, 13, 0, tzinfo=timezone.utc), details={"serial": 2, "reason": "rash"})
    body = calendar_service.google_event_body(record, merchant, item)
    assert body["summary"] == "Ann · Dr. Nair" and body["start"]["timeZone"] == "America/New_York"
    assert body["extendedProperties"]["private"][calendar_service.EVENT_TAG] == "rec-1"
    end = datetime.fromisoformat(body["end"]["dateTime"]) - datetime.fromisoformat(body["start"]["dateTime"])
    assert end == timedelta(minutes=15) and "Reason: rash" in body["description"]


@pytest.mark.asyncio
async def test_busy_times_for_a_call_are_cached(monkeypatch):
    memo.clear()
    fetched: list[str] = []

    async def fake_fetch(url, **kwargs):
        fetched.append(url)
        return [(datetime(2026, 10, 6, 9, tzinfo=NY), datetime(2026, 10, 6, 10, tzinfo=NY))]

    monkeypatch.setattr(calendar_service, "fetch_ics_busy", fake_fetch)
    merchant = SimpleNamespace(id="m-cache", timezone="America/New_York", region="US", calendar_settings={"busy_ics_urls": ["https://cal.example/a.ics"]})
    doctor = CatalogEntry("d1", "D1", "doctor", "Dr. X", {"calendar_ics": "webcal://cal.example/d.ics"})
    first = await calendar_service.busy_for(merchant, [doctor], days=14)
    second = await calendar_service.busy_for(merchant, [doctor], days=14)
    assert set(first) == {"", "d1"} and first == second and len(fetched) == 2
    memo.clear()
