"""Dental and vet on the clinic engine: their own wording, intake fields, emergencies, read-backs
and commits — driven through the real tools + runtime with the model's tool calls scripted."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.timefmt import business_tz
from app.verticals import flow_for, get_vertical
from app.voice.tools import CallTools, NullCallStore

NY = business_tz("America/New_York")
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=NY)  # Friday 8 pm

DENTISTS = [
    CatalogEntry("den-park", "D1", "doctor", "Dr. Emily Park", {"specialty": "General Dentistry", "days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 30, "fee": 95}),
    CatalogEntry("den-patel", "D2", "doctor", "Dr. Raj Patel", {"specialty": "Orthodontics", "days": ["tue", "thu"], "start_time": "10:00", "end_time": "16:00", "slot_minutes": 30, "fee": 150}),
]
VETS = [
    CatalogEntry("vet-lee", "D1", "doctor", "Dr. Hannah Lee", {"specialty": "General Practice", "days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 20, "fee": 80}),
]


@dataclass
class Account:
    vertical: str
    business_name: str = "Test Co"
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
    kind: str = "appointment"


def _call(vertical: str, catalog: list[CatalogEntry], direction: str = DIRECTION_INBOUND, *, config: dict | None = None, **ctx_kwargs: Any):
    merchant = Account(vertical, vertical_config=config or {})
    ctx = CallContext(merchant=merchant, catalog=list(catalog), direction=direction, now=NOW, **ctx_kwargs)
    runtime = FlowRuntime(flow_for(merchant, direction), ctx, language="en")
    store = NullCallStore()
    return CallTools(runtime, store), runtime, store


# ---------------------------------------------------------------------------- dental
@pytest.mark.asyncio
async def test_dental_asks_for_a_dentist_in_its_own_words():
    tools, runtime, _ = _call("dental", DENTISTS, caller_number="+16175550100")
    result = await tools.execute("save_details", {"intent": "book"}, caller_text="I'd like an appointment")
    assert runtime.stage == "doctor" and result.say == "Which dentist would you like to see? We have General Dentistry and Orthodontics."


@pytest.mark.asyncio
async def test_dental_volunteered_details_skip_their_questions_and_insurance_reaches_the_record():
    tools, runtime, store = _call("dental", DENTISTS, caller_number="+16175550100")
    result = await tools.execute(
        "save_details",
        {"intent": "book", "doctor": "D1", "date": "2026-10-05", "time_pref": "10:00", "patient_name": "Ana Lopez", "insurance": "Delta Dental", "reason": "cleaning"},
        caller_text="A cleaning with Dr Park on Monday at 10, I'm Ana Lopez, I have Delta Dental",
    )
    # Dentist, day, name and insurance were all given; caller ID covers the phone → straight to the read-back.
    assert runtime.stage == "confirm" and "Dr. Emily Park for Ana Lopez" in result.say and "10 AM" in result.say and "95 dollars" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes please")
    assert result.outcome == "booked" and result.say.endswith("Please arrive a few minutes early. Is there anything else I can help you with?")
    action = store.commits[0]["action"]
    assert action.fields["customer_name"] == "Ana Lopez" and action.fields["kind"] == "appointment"
    assert action.fields["details"]["insurance"] == "Delta Dental" and action.fields["details"]["reason"] == "cleaning"
    assert action.capacity == ("den-park", datetime(2026, 10, 5, 10, 0, tzinfo=NY), 1)


@pytest.mark.asyncio
async def test_dental_asks_insurance_once_by_default():
    tools, runtime, _ = _call("dental", DENTISTS, caller_number="+16175550100")
    result = await tools.execute("save_details", {"intent": "book", "doctor": "D2", "date": "2026-10-06", "patient_name": "Leo"}, caller_text="braces consult Tuesday, Leo")
    assert runtime.stage == "insurance" and result.say.endswith("Do you have dental insurance? If so, which provider?")
    result = await tools.execute("save_details", {"reply": "No problem."}, caller_text="I'd rather not say")
    assert runtime.stage == "confirm" and "Dr. Raj Patel" in result.say


@pytest.mark.asyncio
async def test_dental_emergency_keeps_the_tooth_in_milk():
    tools, _, store = _call("dental", DENTISTS)
    result = await tools.execute("report_emergency", {"what": "knocked-out tooth"}, caller_text="my son's tooth got knocked out")
    assert result.outcome == "emergency" and "call nine one one" in result.say and "keep it in milk" in result.say


# ---------------------------------------------------------------------------- vet
@pytest.mark.asyncio
async def test_vet_takes_owner_then_pet_and_books_for_the_pet():
    tools, runtime, store = _call("vet", VETS, caller_number="+16175550133")
    result = await tools.execute("save_details", {"intent": "book", "date": "2026-10-05", "time_pref": "09:00"}, caller_text="vaccination on Monday morning")
    # One vet: no question about who; the owner's name comes first, then the pet.
    assert runtime.stage == "owner_name" and result.say.endswith("May I have your name?")
    result = await tools.execute("save_details", {"owner_name": "Sam Rivera"}, caller_text="Sam Rivera")
    assert runtime.stage == "pet_name" and result.say.endswith("And what's your pet's name?")
    result = await tools.execute("save_details", {"pet_name": "Bella"}, caller_text="Bella")
    assert runtime.stage == "species" and "a dog, a cat, a bird, a rabbit" in result.say
    result = await tools.execute("save_details", {"species": "dog"}, caller_text="she's a dog")
    assert runtime.stage == "confirm" and result.say.startswith("So that's Dr. Hannah Lee for Bella, Monday")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "booked" and "on a leash or in a carrier" in result.say
    fields = store.commits[0]["action"].fields
    assert fields["customer_name"] == "Sam Rivera" and fields["customer_phone"] == "+16175550133"
    assert fields["details"]["pet_name"] == "Bella" and fields["details"]["species"] == "dog"
    assert fields["items_summary"] == "Dr. Hannah Lee — Bella (dog)"


@pytest.mark.asyncio
async def test_vet_emergency_sends_the_pet_to_the_emergency_vet():
    tools, _, _ = _call("vet", VETS)
    result = await tools.execute("report_emergency", {"what": "ate chocolate"}, caller_text="my dog ate a whole bar of chocolate")
    assert result.outcome == "emergency" and result.say == "This sounds like an emergency. Please take your pet to the nearest emergency vet right away."
    tools, _, _ = _call("vet", VETS, config={"emergency_vet": "Northside Animal ER on 5th Avenue"})
    result = await tools.execute("report_emergency", {"what": "hit by a car"}, caller_text="my cat was hit by a car")
    assert "take your pet to Northside Animal ER on 5th Avenue right away" in result.say


@pytest.mark.asyncio
async def test_vet_reminder_names_the_pet():
    record = Record("a-9", "Sam Rivera", "+16175550133", catalog_item_id="vet-lee", scheduled_at=datetime(2026, 10, 5, 9, 20, tzinfo=NY), details={"pet_name": "Bella"})
    tools, runtime, store = _call("vet", VETS, DIRECTION_OUTBOUND, record=record)
    result = await tools.execute("save_details", {"identity_confirmed": True}, caller_text="yes speaking")
    assert result.say.startswith("Bella has an appointment with Dr. Hannah Lee on Monday, October 5 at 9:20 AM")
    result = await tools.execute("save_details", {"attend": True}, caller_text="yes we'll be there")
    assert result.outcome == "confirmed" and store.commits[0]["action"].record_id == "a-9"


def test_dental_and_vet_declare_their_own_forms():
    dental, vet = get_vertical("dental"), get_vertical("vet")
    assert dental.catalog_label["en"] == "Dentist" and vet.catalog_label["en"] == "Vet"
    assert any(spec.key == "insurance" for spec in dental.record_fields)
    assert any(spec.key == "pet_name" and spec.required for spec in vet.record_fields)
    assert any(spec.key == "emergency_vet" for spec in vet.config_fields)
    assert set(dental.directions) == set(vet.directions) == {"inbound", "outbound"} and dental.as_json()["configurable_flow"]
