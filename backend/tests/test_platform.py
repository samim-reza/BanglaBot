"""Platform pieces: scheduling, time phrasing, regions, forms, prompts, chat sessions, webhooks."""

from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

from app.core.regions import get_region, normalize_phone, region_defaults
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.scheduling import Availability, Window, free_slots, pick_slot, slot_key
from app.flows.timefmt import business_tz, date_phrase, days_phrase, parse_date, snap_weekday, spoken_digits, time_phrase
from app.verticals import VERTICALS, flow_for, get_vertical
from app.verticals.forms import FieldError, clean_config, split_catalog, split_record
from app.voice.llm import LLMReply, LLMToolCall
from app.voice.prompts import build_messages
from app.voice.text_session import TextSession
from app.voice.tools import NullCallStore

NY = business_tz("America/New_York")


# ---------------------------------------------------------------------------- scheduling
def test_slots_respect_lead_time_capacity_and_max_patients():
    window = Window(start=time(9, 0), end=time(10, 0), days=frozenset({"mon"}), step_minutes=15, max_slots=3)
    now = datetime(2026, 10, 5, 8, 40, tzinfo=NY)  # a Monday; earliest bookable = 9:10
    booked = {slot_key("d1", datetime(2026, 10, 5, 9, 30, tzinfo=NY)): 1}
    slots = free_slots([window], date(2026, 10, 5), now=now, item_id="d1", booked=booked, lead_minutes=30)
    # 9:00 is inside the 30-minute lead, 9:30 is taken, max 3 serials (9:00, 9:15, 9:30).
    assert [(s.start.time(), s.serial) for s in slots] == [(time(9, 15), 2)]


def test_pick_slot_prefers_the_named_window_or_the_nearest_time_after_the_preference():
    windows = [
        Window(start=time(9, 0), end=time(12, 0), key="morning", capacity=2),
        Window(start=time(12, 0), end=time(15, 0), key="afternoon", capacity=2),
    ]
    now = datetime(2026, 10, 5, 6, 0, tzinfo=NY)
    slots = free_slots(windows, date(2026, 10, 5), now=now)
    assert pick_slot(slots, window_key="afternoon").window.key == "afternoon"
    hourly = free_slots([Window(start=time(9, 0), end=time(13, 0), step_minutes=60)], date(2026, 10, 5), now=now)
    assert pick_slot(hourly, "10:40").start.time() == time(11, 0)
    assert pick_slot(hourly, None).start.time() == time(9, 0)


def test_availability_next_days_skips_closed_and_full_days():
    window = Window(start=time(9, 0), end=time(10, 0), days=frozenset({"tue", "thu"}), step_minutes=60)
    availability = Availability(windows=[window], item_id="d1", horizon_days=14)
    now = datetime(2026, 10, 5, 8, 0, tzinfo=NY)
    booked = {slot_key("d1", datetime(2026, 10, 6, 9, 0, tzinfo=NY)): 1}
    assert availability.next_days(now=now, booked=booked, limit=2) == [date(2026, 10, 8), date(2026, 10, 13)]


# ---------------------------------------------------------------------------- time phrasing
def test_dates_and_times_read_naturally():
    today = date(2026, 10, 2)
    assert date_phrase(date(2026, 10, 5), today, "en", month_first=True) == "Monday, October 5"
    assert date_phrase(date(2026, 10, 5), today, "en") == "Monday, 5 October"
    assert date_phrase(date(2026, 10, 3), today, "bn") == "আগামীকাল, শনিবার"
    assert time_phrase(time(18, 20), "bn", at=True) == "সন্ধ্যা ছয়টা বিশ মিনিটে"
    assert time_phrase(time(14, 30), "en") == "2:30 PM"
    assert days_phrase(["mon", "tue", "wed", "thu", "fri", "sat"], "en") == "Monday to Saturday"
    assert days_phrase(["sat", "mon", "wed"], "en") == "Monday, Wednesday and Saturday"
    assert days_phrase(["sat", "mon", "wed"], "bn") == "শনি, সোম ও বুধবার"
    assert parse_date("tomorrow", today) == date(2026, 10, 3)
    assert snap_weekday(date(2026, 10, 10), "Saturday please", today) == date(2026, 10, 3)
    assert snap_weekday(date(2026, 10, 10), "next Saturday", today) == date(2026, 10, 10)
    assert spoken_digits("+1 415 555 0123", "en") == "plus one, four one five, five five five, zero one two three"


# ---------------------------------------------------------------------------- regions
def test_region_presets_and_phone_normalization():
    assert region_defaults("GB") == {"region": "GB", "timezone": "Europe/London", "currency": "GBP", "emergency_number": "999"}
    assert get_region("nope").code == "INTL"
    assert normalize_phone("(212) 555-0100", "US") == "+12125550100"
    assert normalize_phone("01712345678", "BD") == "+8801712345678"
    assert normalize_phone("+44 7700 900123", "US") == "+447700900123"


def test_context_takes_clock_currency_and_emergency_from_the_account():
    merchant = SimpleNamespace(region="GB", timezone="Europe/London", currency="", emergency_number="", vertical="clinic")
    ctx = CallContext(merchant=merchant)
    assert ctx.currency == "GBP" and ctx.emergency_number == "999" and str(ctx.now.tzinfo) == "Europe/London"
    assert ctx.say_number("999", "en") == "nine nine nine"
    ctx.channel = "chat"
    assert ctx.say_number("999", "en") == "999"


# ---------------------------------------------------------------------------- forms
def test_record_forms_validate_against_the_vertical():
    clinic = get_vertical("clinic")
    columns, details = split_record(
        clinic,
        {"customer_name": "Ann", "customer_phone": "+1 617 555 0100", "catalog_item_id": "d1", "scheduled_at": "2026-10-05T14:20", "reason": "Follow-up", "hack": "x"},
        tz=NY,
    )
    assert columns["scheduled_at"] == datetime(2026, 10, 5, 14, 20, tzinfo=NY)
    assert details == {"reason": "Follow-up"}
    with pytest.raises(FieldError):
        split_record(clinic, {"customer_name": "Ann", "customer_phone": "+16175550100"})  # doctor + time required
    name, data = split_catalog(clinic, {"name": "Dr. X", "specialty": "ENT", "days": "mon, wed", "start_time": "9", "end_time": "5 pm", "fee": "120"})
    assert name == "Dr. X" and data["days"] == ["mon", "wed"] and data["start_time"] == "09:00" and data["end_time"] == "17:00" and data["fee"] == 120


def test_config_keeps_known_fields_and_valid_time_windows():
    home = get_vertical("home_service")
    config = clean_config(
        home,
        {"service_areas": "Brooklyn\nQueens", "teams": "4", "bogus": 1, "time_windows": [{"key": "Early", "start": "07:00", "end": "10:00"}, {"key": "bad", "start": "x"}]},
    )
    assert config == {"service_areas": ["Brooklyn", "Queens"], "teams": 4, "time_windows": [{"key": "early", "start": "07:00", "end": "10:00"}]}


def test_every_vertical_declares_consistent_specs():
    for vertical in VERTICALS.values():
        spec = vertical.as_json()
        assert spec["record_fields"] and spec["directions"]
        assert all(field["key"] for field in spec["record_fields"])
        if vertical.catalog_kind:
            assert any(field["key"] == "name" for field in spec["catalog_fields"])
        for direction, flow in vertical.flows.items():
            assert flow.direction == direction and flow.slot_properties() is not None


# ---------------------------------------------------------------------------- prompts / caching
def test_prompt_prefix_is_identical_across_callers_of_the_same_business():
    merchant = SimpleNamespace(
        vertical="clinic", business_name="CityCare", language="en", region="US", timezone="America/New_York", currency="USD",
        emergency_number="911", knowledge="Open 8-6.", support_phone="", custom_greeting="", vertical_config={},
    )
    flow = flow_for(merchant, DIRECTION_INBOUND)
    first = build_messages(flow, CallContext(merchant=merchant, direction=DIRECTION_INBOUND, caller_number="+1"), opening="Hi")
    second = build_messages(flow, CallContext(merchant=merchant, direction=DIRECTION_INBOUND, caller_number="+2"), opening="Hi")
    assert first[0] == second[0] and first[1] == second[1] and first[2] != second[2]
    assert "Open 8-6." in first[1]["content"] and "Speak only English" in first[0]["content"]


# ---------------------------------------------------------------------------- chat session
class ScriptedLLM:
    def __init__(self, replies: list[LLMReply]) -> None:
        self.replies = list(replies)
        self.prompt_tokens = self.completion_tokens = self.cached_prompt_tokens = 0

    async def complete(self, messages, **kwargs):
        return self.replies.pop(0)


@pytest.mark.asyncio
async def test_text_session_runs_the_same_engine_as_a_call():
    merchant = SimpleNamespace(
        id="m1", vertical="ecommerce", business_name="Urban Threads", language="en", region="US", timezone="America/New_York",
        currency="USD", emergency_number="911", knowledge="", support_phone="+1999", custom_greeting="", vertical_config={},
    )
    ctx = CallContext(merchant=merchant, direction=DIRECTION_INBOUND, caller_number="+14155550123", channel="chat")
    store = NullCallStore()
    llm = ScriptedLLM(
        [
            LLMReply(content="", tool_calls=[LLMToolCall("c1", "save_details", '{"message": "Where is my order", "caller_name": "Emily"}')]),
        ]
    )
    session = TextSession(merchant=merchant, ctx=ctx, flow=flow_for(merchant, DIRECTION_INBOUND), store=store, call_log_id="log", llm=llm)
    opening = await session.start()
    assert opening == ["Hi, welcome to Urban Threads! How can I help you today?"]
    reply = await session.say("where is my order? I'm Emily")
    assert len(reply) == 1 and "A team member will call you back on this number" in reply[0]
    reply = await session.say("yes")  # read-back confirmed on the fast path, no model needed
    assert session.ended and reply == ["Thank you. One of our team will get in touch with you shortly. Goodbye."]
    assert store.commits[0]["action"].fields["kind"] == "message"
    assert store.transcripts and store.usage


# ---------------------------------------------------------------------------- webhooks
def test_webhook_signature_is_hmac_sha256_of_the_body():
    import hashlib
    import hmac

    from app.services.webhook_service import sign

    body = b'{"event":"test"}'
    assert sign("secret", body) == "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()


def test_named_days_are_read_from_the_callers_words():
    from app.flows.timefmt import date_from_text

    friday = date(2026, 10, 2)
    assert date_from_text("I want the children's doctor on Wednesday morning", friday) == date(2026, 10, 7)
    assert date_from_text("আমি শিশু ডাক্তার দেখাতে চাই বুধবার সকালে", friday) == date(2026, 10, 7)
    assert date_from_text("কাল সকালে আসব", friday) == date(2026, 10, 3)
    assert date_from_text("tomorrow please", friday) == date(2026, 10, 3)
    assert date_from_text("next Friday", date(2026, 10, 5)) == date(2026, 10, 16)
    assert date_from_text("Wednesday or Thursday", friday) is None
    assert date_from_text("I'd like a house", friday) is None
