"""The custom (build-your-own) engine through the real tools + runtime, scripted model calls (no model,
no database): the owner's own intake questions, optional ones asked once, bookings over resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.timefmt import business_tz
from app.verticals import flow_for, get_vertical
from app.voice.tools import CallTools, NullCallStore

NY = business_tz("America/New_York")
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=NY)  # Friday noon

INTAKE = {
    "steps": {
        "intake": {
            "options": {
                "custom": [
                    {"key": "level", "label": "Experience level", "question": "Beginner, intermediate or advanced?", "type": "choice",
                     "choices": ["beginner", "intermediate", "advanced"], "required": True},
                    {"key": "injuries", "label": "Injuries", "question": "Any injuries we should know about?", "type": "text"},
                ]
            }
        }
    }
}

RESOURCES = [
    CatalogEntry("r-private", "I1", "resource", "Private session", {"days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 60, "capacity": 1, "price": 80}),
    CatalogEntry("r-group", "I2", "resource", "Group class", {"days": ["mon", "tue", "wed", "thu", "fri", "sat"], "start_time": "18:00", "end_time": "20:00", "slot_minutes": 60, "capacity": 12, "price": 20}),
]


@dataclass
class Account:
    vertical: str = "custom"
    business_name: str = "Harbor Yoga"
    language: str = "en"
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"
    custom_greeting: str = ""
    support_phone: str = ""
    knowledge: str = ""
    vertical_config: dict = field(default_factory=dict)
    voice_persona: str = "female"
    agent_flow: dict = field(default_factory=lambda: INTAKE)
    agent_flow_locks: dict = field(default_factory=dict)
    id: str = "m1"


def _call(catalog: list[CatalogEntry] | None = None, **merchant: Any) -> tuple[CallTools, FlowRuntime, NullCallStore]:
    account = Account(**merchant)
    ctx = CallContext(merchant=account, catalog=list(RESOURCES if catalog is None else catalog), direction=DIRECTION_INBOUND, now=NOW, caller_number="+16465550100")
    runtime = FlowRuntime(flow_for(account, DIRECTION_INBOUND), ctx, language="en")
    store = NullCallStore()
    return CallTools(runtime, store), runtime, store


@pytest.mark.asyncio
async def test_inquiry_asks_the_owners_questions_and_an_optional_one_only_once():
    tools, runtime, store = _call()
    result = await tools.execute("save_details", {"intent": "inquiry"}, caller_text="I have a question for the team")
    assert result.say == "May I have your name?"
    result = await tools.execute("save_details", {"customer_name": "Ana"}, caller_text="Ana")
    assert result.say == "Beginner, intermediate or advanced?" and runtime.stage == "f_level"
    result = await tools.execute("save_details", {"f_level": "Beginner"}, caller_text="beginner")
    assert result.say == "Any injuries we should know about?"
    # They skip the optional question: it is not asked again — straight to the read-back.
    result = await tools.execute("save_details", {"note": "wants to try a class"}, caller_text="no, I just want to try a class")
    assert runtime.stage == "confirm"
    assert result.say == "So I'll pass your details to our team: Ana, Experience level: beginner, wants to try a class. They'll get back to you on this number. Is that right?"
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "lead" and result.say.startswith("Thanks — our team will get back to you soon.")
    action = store.commits[0]["action"]
    assert action.fields["kind"] == "lead" and action.fields["customer_name"] == "Ana"
    assert action.fields["details"]["intake"] == {"f_level": "beginner"} and action.fields["details"]["type"] == "inquiry"


@pytest.mark.asyncio
async def test_a_required_custom_field_keeps_being_asked():
    tools, runtime, _ = _call()
    await tools.execute("save_details", {"intent": "inquiry", "customer_name": "Ana"}, caller_text="Ana, a question")
    result = await tools.execute("save_details", {"f_level": "expert"}, caller_text="expert")  # not one of the choices
    assert runtime.stage == "f_level" and result.say == "Beginner, intermediate or advanced?"


@pytest.mark.asyncio
async def test_booking_branch_schedules_over_the_resource_and_books_with_its_capacity():
    tools, runtime, store = _call()
    result = await tools.execute("save_details", {"intent": "book"}, caller_text="I'd like to book")
    assert result.say == "What would you like to book? We have Private session and Group class."
    result = await tools.execute("save_details", {"resource": "group class", "date": "2026-10-03", "time_pref": "18:00"}, caller_text="the group class tomorrow, Saturday at 6")
    assert runtime.slots["slot"] == datetime(2026, 10, 3, 18, 0, tzinfo=NY).isoformat() and result.say == "May I have your name?"
    await tools.execute("save_details", {"customer_name": "Ben"}, caller_text="Ben")
    await tools.execute("save_details", {"f_level": "advanced"}, caller_text="advanced")
    result = await tools.execute("save_details", {"f_injuries": "none"}, caller_text="none")
    assert result.say == "So that's Group class for Ben, tomorrow, Saturday at 6 PM. Shall I book it?"
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes please")
    assert result.outcome == "booked" and result.say.startswith("You're booked for tomorrow, Saturday at 6 PM.")
    action = store.commits[0]["action"]
    assert action.fields["kind"] == "booking" and action.fields["catalog_item_id"] == "r-group" and action.fields["total_amount"] == 20
    assert action.capacity == ("r-group", datetime(2026, 10, 3, 18, 0, tzinfo=NY), 12)
    assert action.fields["details"]["intake"] == {"f_level": "advanced", "f_injuries": "none"}


@pytest.mark.asyncio
async def test_a_closed_day_is_refused_and_nothing_bookable_becomes_a_message():
    tools, runtime, _ = _call()
    result = await tools.execute("save_details", {"intent": "book", "resource": "I1", "date": "2026-10-04"}, caller_text="private session on Sunday")
    assert "isn't available on Sunday" in result.say and runtime.stage == "date"  # the resource, not "we're closed"
    tools, runtime, _ = _call(catalog=[])
    result = await tools.execute("save_details", {"intent": "book"}, caller_text="I want to book")
    assert runtime.slots["intent"] == "message" and result.say == "Sure — what message should I pass on to the team?"


@pytest.mark.asyncio
async def test_without_custom_fields_only_the_name_is_asked():
    tools, runtime, store = _call(agent_flow={})
    await tools.execute("save_details", {"intent": "message", "message": "Do you have gift cards?"}, caller_text="do you have gift cards")
    result = await tools.execute("save_details", {"customer_name": "Cy"}, caller_text="Cy")
    assert result.say == "So I'll pass this on to our team: Do you have gift cards. They'll call you back on this number. Is that right?"


def test_custom_vertical_declares_generic_resources():
    vertical = get_vertical("custom")
    assert vertical.catalog_kind == "resource" and vertical.record_kind == "booking" and vertical.as_json()["configurable_flow"]
    assert {"days", "start_time", "end_time", "slot_minutes", "capacity"} <= {f.key for f in vertical.catalog_fields}
