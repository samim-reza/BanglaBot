"""Salon & spa: services + staff (two catalog kinds), "anyone" gets a person, duration-aware times,
per-staff capacity, optional deposit and cancellation policy, moving and cancelling bookings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.flows import hearing
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.scheduling import slot_key
from app.flows.timefmt import business_tz
from app.verticals import flow_for, get_vertical
from app.verticals.forms import FieldError, split_catalog
from app.voice.tools import CallTools, NullCallStore

NY = business_tz("America/New_York")
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=NY)  # Friday 8 pm

CATALOG = [
    CatalogEntry("svc-cut", "S1", "service", "Haircut", {"duration_minutes": 45, "price": 45, "staff": ["Maya", "Leo"]}),
    CatalogEntry("svc-color", "S2", "service", "Balayage color", {"duration_minutes": 120, "price": 180, "staff": ["Maya"]}),
    CatalogEntry("svc-brow", "S3", "service", "Eyebrow threading", {"duration_minutes": 15, "price": 15}),
    CatalogEntry("st-maya", "T1", "staff", "Maya", {"days": ["tue", "wed", "thu", "fri", "sat"], "start_time": "10:00", "end_time": "18:00"}),
    CatalogEntry("st-leo", "T2", "staff", "Leo", {"days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "services": ["Haircut"]}),
]


@dataclass
class Account:
    vertical: str = "salon"
    business_name: str = "Glow Studio"
    language: str = "en"
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"
    custom_greeting: str = ""
    support_phone: str = ""
    knowledge: str = ""
    vertical_config: dict = field(default_factory=dict)
    sms_settings: dict = field(default_factory=dict)
    agent_flow: dict = field(default_factory=dict)
    agent_flow_locks: dict = field(default_factory=dict)
    id: str = "m1"


@dataclass
class Record:
    id: str
    customer_name: str
    customer_phone: str
    catalog_item_id: str | None = None
    scheduled_at: datetime | None = None
    details: dict = field(default_factory=dict)
    kind: str = "booking"


def _call(agent_flow: dict | None = None, **ctx_kwargs: Any):
    merchant = Account(agent_flow=agent_flow or {})
    ctx_kwargs.setdefault("caller_number", "+12125550111")
    ctx = CallContext(merchant=merchant, catalog=list(CATALOG), direction=DIRECTION_INBOUND, now=NOW, **ctx_kwargs)
    runtime = FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en")
    store = NullCallStore()
    return CallTools(runtime, store), runtime, store


def steps(**skills: dict) -> dict:
    return {"_v": 1, "steps": skills}


BOOK_MAYA = {"intent": "book", "service": "S1", "staff": "Maya", "date": "2026-10-06", "time_pref": "11:00", "customer_name": "Ana"}


# ---------------------------------------------------------------------------- booking
@pytest.mark.asyncio
async def test_volunteered_details_go_straight_to_the_read_back_and_book_per_staff():
    tools, runtime, store = _call()
    result = await tools.execute("save_details", dict(BOOK_MAYA), caller_text="A haircut with Maya on Tuesday at 11, I'm Ana")
    assert runtime.stage == "confirm"
    assert result.say == "So that's a Haircut with Maya, Tuesday, October 6 at 11 AM. It's 45 dollars. Shall I book it?"
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes please")
    assert result.outcome == "booked" and result.say.startswith("You're all set — a Haircut with Maya")
    action = store.commits[0]["action"]
    start = datetime(2026, 10, 6, 11, 0, tzinfo=NY)
    assert action.fields["kind"] == "booking" and action.fields["catalog_item_id"] == "st-maya" and action.fields["total_amount"] == 45
    assert action.fields["details"]["service"] == "Haircut" and action.fields["details"]["duration_minutes"] == 45
    assert action.capacity == ("st-maya", start, 1)


@pytest.mark.asyncio
async def test_anyone_gets_the_earliest_free_person_who_does_the_service():
    tools, runtime, store = _call()
    result = await tools.execute(
        "save_details", {"intent": "book", "service": "S1", "staff": "anyone", "date": "2026-10-05", "customer_name": "Bo"}, caller_text="a haircut Monday, anyone, Bo"
    )
    # Maya is off on Mondays; Leo starts at 9.
    assert runtime.slots["staff"] == "any" and "a Haircut with Leo, Monday, October 5 at 9 AM" in result.say
    await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert store.commits[0]["action"].fields["catalog_item_id"] == "st-leo"


@pytest.mark.asyncio
async def test_staff_question_is_skipped_when_only_one_person_does_it():
    tools, runtime, _ = _call()
    result = await tools.execute("save_details", {"intent": "book", "service": "S3"}, caller_text="eyebrow threading please")
    assert runtime.slots["staff"] == "T1" and runtime.stage == "date"
    assert result.say == "Maya works Tuesday to Saturday 10 AM to 6 PM. Which day would you like?"


@pytest.mark.asyncio
async def test_staff_who_does_not_do_the_service_is_refused():
    tools, runtime, _ = _call()
    await tools.execute("save_details", {"intent": "book", "service": "S2"}, caller_text="balayage")
    result = await tools.execute("save_details", {"staff": "Leo"}, caller_text="with Leo")
    assert result.say.startswith("Sorry, Leo doesn't do Balayage color. Maya can")
    assert runtime.slots["staff"] == "T1"


@pytest.mark.asyncio
async def test_a_long_service_must_fit_before_the_stylist_leaves():
    tools, runtime, _ = _call()
    result = await tools.execute(
        "save_details", {"intent": "book", "service": "S2", "date": "2026-10-06", "time_pref": "17:00", "customer_name": "Cy"}, caller_text="balayage Tuesday at 5, Cy"
    )
    # 120 minutes from 5 PM runs past 6 PM: the nearest start that fits is 4 PM.
    assert runtime.slots["slot"] == datetime(2026, 10, 6, 16, 0, tzinfo=NY).isoformat() and "4 PM" in result.say


@pytest.mark.asyncio
async def test_an_existing_booking_blocks_overlapping_times():
    taken = {slot_key("st-maya", datetime(2026, 10, 6, 12, 0, tzinfo=NY)): 1}
    tools, runtime, _ = _call(booked=taken)
    await tools.execute(
        "save_details", {"intent": "book", "service": "S1", "staff": "T1", "date": "2026-10-06", "time_pref": "12:30", "customer_name": "Di"}, caller_text="haircut with Maya Tuesday 12:30"
    )
    # Maya's 12:00 booking may run as long as her longest service (2 h): 2 PM is the nearest start after it.
    assert runtime.slots["slot"] == datetime(2026, 10, 6, 14, 0, tzinfo=NY).isoformat()


# ---------------------------------------------------------------------------- optional skills
@pytest.mark.asyncio
async def test_online_deposit_switched_on_holds_the_booking_as_pending():
    flow = steps(payment={"enabled": True, "options": {"mode": "online_required", "amount_source": "deposit", "deposit_amount": 20}})
    tools, runtime, store = _call(flow)
    result = await tools.execute("save_details", dict(BOOK_MAYA), caller_text="A haircut with Maya on Tuesday at 11, I'm Ana")
    assert runtime.stage == "confirm" and "payment link for 20 dollars" in result.say and "30 minutes" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    action = store.commits[0]["action"]
    assert result.outcome == "booked" and action.status == "pending"
    assert action.fields["details"]["payment"]["method"] == "online" and action.fields["details"]["payment"]["amount"] == 20
    assert "link in your texts" in result.say


@pytest.mark.asyncio
async def test_separate_cancellation_policy_needs_its_own_yes():
    tools, runtime, store = _call(steps(consent={"enabled": True, "options": {"mode": "separate"}}))
    result = await tools.execute("save_details", dict(BOOK_MAYA), caller_text="A haircut with Maya on Tuesday at 11, I'm Ana")
    assert runtime.stage == "consent" and result.say == "Please note: we need 24 hours' notice to cancel or move a booking. Is that okay?"
    result = await tools.execute("save_details", {"consent": True}, caller_text="hmm maybe")
    assert "consent" in result.payload.get("rejected", []) and runtime.stage == "consent"
    await tools.execute("save_details", {"consent": True}, caller_text="yes I agree")
    assert runtime.stage == "confirm"
    await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert "text_sha256" in store.commits[0]["action"].fields["details"]["consent"]


# ---------------------------------------------------------------------------- existing bookings
def _booking() -> Record:
    return Record("b-1", "Ana", "+12125550111", catalog_item_id="st-maya", scheduled_at=datetime(2026, 10, 6, 10, 0, tzinfo=NY), details={"service": "Haircut", "service_id": "svc-cut"})


@pytest.mark.asyncio
async def test_moving_a_booking_keeps_the_service_and_the_stylist():
    tools, runtime, store = _call(caller_records=[_booking()])
    result = await tools.execute("save_details", {"intent": "reschedule"}, caller_text="I need to move my appointment")
    assert runtime.stage == "date" and result.say.startswith("Maya works Tuesday to Saturday")
    result = await tools.execute("save_details", {"date": "2026-10-07", "time_pref": "14:00"}, caller_text="Wednesday at 2")
    assert result.say == "So I'll move your Haircut with Maya to Wednesday, October 7 at 2 PM. Is that right?"
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    action = store.commits[0]["action"]
    assert result.outcome == "rescheduled" and action.record_id == "b-1" and action.capacity == ("st-maya", datetime(2026, 10, 7, 14, 0, tzinfo=NY), 1)


@pytest.mark.asyncio
async def test_cancelling_a_booking_found_by_phone():
    tools, runtime, store = _call(caller_records=[_booking()])
    result = await tools.execute("save_details", {"intent": "cancel"}, caller_text="cancel my haircut")
    assert result.say == "Shall I cancel your Haircut with Maya, on Tuesday, October 6 at 10 AM?"
    fields = runtime.flow.fast_fields(runtime.stage, "Yes, cancel it", hearing.classify("Yes, cancel it"), runtime.slots, runtime.ctx)
    result = await tools.execute("save_details", fields, caller_text="Yes, cancel it")
    assert result.outcome == "cancelled" and store.commits[0]["action"].record_id == "b-1"


# ---------------------------------------------------------------------------- the two catalog kinds
def test_salon_declares_services_and_staff_as_catalog_kinds():
    salon = get_vertical("salon")
    kinds = salon.as_json()["catalog_kinds"]
    assert [(k["kind"], k["ref_prefix"]) for k in kinds] == [("service", "S"), ("staff", "T")]
    assert salon.catalog_kind == "service" and salon.catalog_fields == salon.catalog_spec("service").fields
    name, data = split_catalog(salon, {"name": "Maya", "days": "tue, wed", "start_time": "10", "end_time": "6 pm"}, kind="staff")
    assert name == "Maya" and data["days"] == ["tue", "wed"] and data["start_time"] == "10:00" and data["end_time"] == "18:00"
    with pytest.raises(FieldError):
        split_catalog(salon, {"name": "X"}, kind="table")
    record_field = next(spec for spec in salon.record_fields if spec.key == "catalog_item_id")
    assert record_field.as_json()["catalog_kind"] == "staff"
    # One-kind verticals keep working unchanged.
    clinic = get_vertical("clinic")
    assert [(k.kind, k.prefix) for k in clinic.kinds] == [("doctor", "D")]
