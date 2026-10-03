"""The business engines driven through the real tools + runtime, with the model's
tool calls scripted (no model, no database): clinic, real estate, home service,
reception — bookings, read-backs, conflicts, cancellations, safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from app.flows import hearing
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.scheduling import slot_key
from app.flows.timefmt import business_tz
from app.verticals import flow_for
from app.voice.tools import CallTools, NullCallStore, answer_only

NY = business_tz("America/New_York")
#: Friday 2 October 2026, 8 pm in New York.
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=NY)


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
    voice_persona: str = "female"
    id: str = "m1"


@dataclass
class Record:
    id: str
    customer_name: str
    customer_phone: str
    kind: str = "appointment"
    catalog_item_id: str | None = None
    scheduled_at: datetime | None = None
    details: dict = field(default_factory=dict)
    address: str = ""
    items_summary: str = ""
    total_amount: Decimal = Decimal("0")
    currency: str = "USD"
    status: str = "pending"


DOCTORS = [
    CatalogEntry("doc-mitchell", "D1", "doctor", "Dr. Sarah Mitchell", {"specialty": "Family Medicine", "days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 20, "fee": 150}),
    CatalogEntry("doc-carter", "D2", "doctor", "Dr. James Carter", {"specialty": "Pediatrics", "days": ["mon", "wed", "fri"], "start_time": "10:00", "end_time": "16:00", "slot_minutes": 20, "fee": 140}),
    CatalogEntry("doc-nair", "D3", "doctor", "Dr. Priya Nair", {"specialty": "Dermatology", "days": ["tue", "thu", "sat"], "start_time": "09:00", "end_time": "13:00", "slot_minutes": 15, "fee": 180}),
]
LISTINGS = [
    CatalogEntry("p-maple", "P1", "property", "3-bed family home, Maple Grove", {"listing_type": "sale", "property_type": "house", "location": "Maple Grove", "price": 485000}),
    CatalogEntry("p-condo", "P2", "property", "Modern 1-bed condo, Downtown", {"listing_type": "rent", "property_type": "flat", "location": "Downtown", "price": 2100}),
]
SERVICES = [
    CatalogEntry("s-ac", "S1", "service", "AC repair", {"category": "HVAC", "visit_charge": 89, "price_from": 120, "price_to": 450}),
    CatalogEntry("s-plumb", "S2", "service", "Plumbing", {"category": "Plumbing", "visit_charge": 79}),
]


def _tools(ctx: CallContext, store: NullCallStore | None = None) -> tuple[CallTools, FlowRuntime, NullCallStore]:
    store = store or NullCallStore()
    flow = flow_for(ctx.merchant, ctx.direction)
    runtime = FlowRuntime(flow, ctx, language=ctx.merchant.language)
    return CallTools(runtime, store), runtime, store


def _clinic(direction: str = DIRECTION_INBOUND, **kwargs: Any) -> CallContext:
    return CallContext(merchant=Account("clinic"), catalog=list(DOCTORS), direction=direction, now=NOW, **kwargs)


# ---------------------------------------------------------------------------- clinic
@pytest.mark.asyncio
async def test_clinic_books_with_one_read_back():
    ctx = _clinic(caller_number="+16175550100")
    tools, runtime, store = _tools(ctx)
    result = await tools.execute(
        "save_details",
        {"intent": "book", "doctor": "D2", "date": "2026-10-07", "time_pref": "morning", "reply": "Of course. Which time suits you?"},
        caller_text="I'd like the children's doctor on Wednesday morning",
    )
    # The question in the model's reply is dropped; the backend asks the next question itself.
    assert result.stop and result.say == "Of course. May I have the patient's name?"
    result = await tools.execute("save_details", {"patient_name": "Leo Carter"}, caller_text="Leo Carter")
    assert "Dr. James Carter" in result.say and "10 AM" in result.say and "140 dollars" in result.say
    assert runtime.stage == "confirm"
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes please")
    assert result.outcome == "booked" and result.hang_up
    action = store.commits[0]["action"]
    assert action.fields["kind"] == "appointment" and action.fields["customer_phone"] == "+16175550100"
    assert action.fields["scheduled_at"] == datetime(2026, 10, 7, 10, 0, tzinfo=NY)
    assert action.capacity == ("doc-carter", datetime(2026, 10, 7, 10, 0, tzinfo=NY), 1)


@pytest.mark.asyncio
async def test_clinic_refuses_a_day_the_doctor_does_not_sit():
    tools, runtime, _ = _tools(_clinic())
    result = await tools.execute("save_details", {"intent": "book", "doctor": "D3", "date": "2026-10-05"}, caller_text="dermatologist on Monday")
    assert "doesn't see patients on Monday" in result.say and "Tuesday, Thursday and Saturday" in result.say
    assert runtime.stage == "date" and "date" not in runtime.slots


@pytest.mark.asyncio
async def test_clinic_slot_taken_at_commit_offers_the_next_one():
    start = datetime(2026, 10, 6, 11, 0, tzinfo=NY)
    store = NullCallStore(taken={slot_key("doc-nair", start)})
    tools, runtime, _ = _tools(_clinic(caller_number="+16175550111"), store)
    await tools.execute("save_details", {"intent": "book", "doctor": "D3", "date": "2026-10-06", "time_pref": "11:00", "patient_name": "Ana Ruiz"}, caller_text="Dermatologist on Tuesday at 11, Ana Ruiz")
    assert runtime.slots["slot"] == start.isoformat()
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    # Someone else booked it between the offer and the yes: apologise, offer the next time.
    assert not result.outcome and "just taken" in result.say and "11:15 AM" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes that's fine")
    assert result.outcome == "booked"
    assert store.commits[-1]["action"].fields["scheduled_at"] == datetime(2026, 10, 6, 11, 15, tzinfo=NY)


@pytest.mark.asyncio
async def test_clinic_cancels_the_callers_appointment_found_by_phone():
    appointment = Record("a-1", "Olivia Brown", "+16175550142", catalog_item_id="doc-carter", scheduled_at=datetime(2026, 10, 5, 10, 40, tzinfo=NY))
    ctx = _clinic(caller_number="+16175550142", caller_records=[appointment])
    tools, runtime, store = _tools(ctx)
    result = await tools.execute("save_details", {"intent": "cancel"}, caller_text="I need to cancel my daughter's appointment")
    assert "Shall I cancel Olivia Brown's appointment with Dr. James Carter" in result.say
    # "Yes, cancel it" is a yes to "shall I cancel?", not a no.
    fields = runtime.flow.fast_fields(runtime.stage, "Yes, cancel it", hearing.classify("Yes, cancel it"), runtime.slots, ctx)
    assert fields == {"confirmed": True}
    result = await tools.execute("save_details", fields, caller_text="Yes, cancel it")
    assert result.outcome == "cancelled"
    assert store.commits[0]["action"].record_id == "a-1" and store.commits[0]["action"].status == "cancelled"


@pytest.mark.asyncio
async def test_clinic_reminder_confirm_or_cancel():
    appointment = Record("a-2", "Robert Wilson", "+16175550199", catalog_item_id="doc-mitchell", scheduled_at=datetime(2026, 10, 5, 14, 20, tzinfo=NY))
    tools, runtime, store = _tools(_clinic(DIRECTION_OUTBOUND, record=appointment))
    assert runtime.stage == "identity"
    result = await tools.execute("save_details", {"identity_confirmed": True}, caller_text="yes speaking")
    assert "You have an appointment with Dr. Sarah Mitchell on Monday, October 5 at 2:20 PM" in result.say
    result = await tools.execute("save_details", {"attend": True}, caller_text="yes I'll be there")
    assert result.outcome == "confirmed" and store.commits[0]["action"].record_id == "a-2"

    tools, runtime, store = _tools(_clinic(DIRECTION_OUTBOUND, record=appointment))
    await tools.execute("save_details", {"identity_confirmed": True}, caller_text="yes")
    await tools.execute("save_details", {"attend": False}, caller_text="no I can't make it")
    result = await tools.execute("save_details", {"wants_new_time": False}, caller_text="no just cancel")
    assert result.outcome == "cancelled"


@pytest.mark.asyncio
async def test_unclear_yes_is_reasked_not_booked():
    tools, runtime, store = _tools(_clinic(caller_number="+16175550100"))
    await tools.execute("save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05", "patient_name": "Jo"}, caller_text="Dr Mitchell Monday, Jo")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="hmm let me think")
    assert not result.outcome and result.say == "Sorry, I didn't quite catch that. Could you say yes or no?"
    assert "confirmed" in result.payload["rejected"] and not store.commits


@pytest.mark.asyncio
async def test_clinic_emergency_tells_the_caller_the_local_number():
    tools, _, store = _tools(_clinic())
    result = await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    assert result.outcome == "emergency" and result.hang_up and "call nine one one" in result.say
    assert store.outcomes[-1]["status"] == "needs_review"


# ---------------------------------------------------------------------------- real estate
def _realty(**kwargs: Any) -> CallContext:
    return CallContext(merchant=Account("real_estate"), catalog=list(LISTINGS), direction=DIRECTION_INBOUND, now=NOW, caller_number="+13055550110", **kwargs)


@pytest.mark.asyncio
async def test_real_estate_buyer_books_a_viewing_scored_hot():
    tools, runtime, store = _tools(_realty())
    await tools.execute("save_details", {"intent": "buy", "property_type": "house", "caller_name": "Chris"}, caller_text="buy a house, I'm Chris")
    await tools.execute("save_details", {"location": "Maple Grove", "budget": "up to 500k", "budget_max": 500000}, caller_text="Maple Grove up to 500k")
    result = await tools.execute("save_details", {"timeline": "1-3 months"}, caller_text="in a month or two")
    # Presenting listings is the model's job (guidance, not a fixed line) — and only fitting ones.
    assert runtime.stage == "listings" and not result.say and "P1" in result.payload["instruction"] and "P2" not in result.payload["instruction"]
    await tools.execute("save_details", {"property": "P1", "wants_visit": True}, caller_text="yes I'd like to see it")
    # "Saturday" said on a Friday means tomorrow, even if the model picked next week.
    result = await tools.execute("save_details", {"visit_date": "2026-10-10", "visit_time_pref": "morning"}, caller_text="Saturday morning")
    assert runtime.slots["visit_date"] == "2026-10-03"
    assert "a viewing of the 3-bed family home, Maple Grove tomorrow at 10 AM" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "booked"
    fields = store.commits[0]["action"].fields
    assert fields["kind"] == "lead" and fields["details"]["lead_score"] == "hot" and fields["catalog_item_id"] == "p-maple"


@pytest.mark.asyncio
async def test_real_estate_seller_becomes_a_lead():
    tools, runtime, store = _tools(_realty())
    await tools.execute("save_details", {"intent": "sell", "property_type": "land", "caller_name": "Rita", "location": "Oak Hills", "size": "one acre"}, caller_text="I want to sell one acre of land in Oak Hills, I'm Rita")
    result = await tools.execute("save_details", {"asking_price": "around 250 thousand"}, caller_text="around 250 thousand")
    assert "So your land in Oak Hills, one acre, asking around 250 thousand" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "lead" and "about selling your property" in result.say
    assert store.commits[0]["action"].status == "needs_review"


# ---------------------------------------------------------------------------- home service
def _home(**kwargs: Any) -> CallContext:
    config = {"service_areas": ["Brooklyn", "Queens"], "teams": 2}
    return CallContext(merchant=Account("home_service", vertical_config=config), catalog=list(SERVICES), direction=DIRECTION_INBOUND, now=NOW, caller_number="+17185550101", **kwargs)


@pytest.mark.asyncio
async def test_home_service_books_an_arrival_window_with_the_call_out_charge():
    tools, runtime, store = _tools(_home())
    await tools.execute("save_details", {"service": "S1", "problem": "AC leaking", "customer_name": "Mark"}, caller_text="my AC is leaking, I'm Mark")
    await tools.execute("save_details", {"address": "42 Bergen St, Brooklyn", "area": "Brooklyn"}, caller_text="42 Bergen St Brooklyn")
    result = await tools.execute("save_details", {"date": "2026-10-03", "time_window": "morning"}, caller_text="tomorrow morning")
    assert "tomorrow between 9 AM and 12 PM" in result.say and "89 dollars" in result.say and "120 dollars to 450 dollars" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="ok yes book it")
    assert result.outcome == "booked"
    action = store.commits[0]["action"]
    assert action.capacity == (None, datetime(2026, 10, 3, 9, 0, tzinfo=NY), 2)
    assert action.fields["details"]["time_window"] == "morning"


@pytest.mark.asyncio
async def test_home_service_outside_the_area_is_refused_and_kept_as_a_lead():
    tools, runtime, store = _tools(_home())
    await tools.execute("save_details", {"service": "S2", "problem": "sink blocked", "customer_name": "Sam"}, caller_text="blocked sink, Sam")
    result = await tools.execute("save_details", {"area": "Hoboken", "address": "1 River St, Hoboken"}, caller_text="Hoboken")
    assert "we don't cover that area" in result.say and "address" not in runtime.slots
    result = await tools.execute("end_call", {"reason": "out of area"}, caller_text="never mind, bye")
    assert result.outcome == "lead" and store.commits[0]["action"].fields["details"]["unfinished"] is True


# ---------------------------------------------------------------------------- reception / misc
@pytest.mark.asyncio
async def test_reception_takes_a_message_for_a_callback():
    ctx = CallContext(merchant=Account("ecommerce"), direction=DIRECTION_INBOUND, now=NOW, caller_number="+14155550123")
    tools, runtime, store = _tools(ctx)
    await tools.execute("save_details", {"message": "Where is my order?"}, caller_text="where is my order")
    result = await tools.execute("save_details", {"caller_name": "Emily"}, caller_text="Emily")
    assert "your message is: Where is my order. A team member will call you back on this number" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "lead" and store.commits[0]["action"].fields["kind"] == "message"


@pytest.mark.asyncio
async def test_inbound_questions_only_end_as_an_inquiry():
    tools, _, store = _tools(_clinic())
    result = await tools.execute("end_call", {"reason": "done"}, caller_text="thanks, that's all")
    assert result.outcome == "inquiry" and result.say == "Thank you for calling. Goodbye."
    assert store.outcomes[-1]["status"] == ""


def test_reply_keeps_answers_and_drops_questions():
    assert answer_only("We open at 8 AM. Would you like to book?") == "We open at 8 AM."
    assert answer_only("Which day suits you?") == ""


def test_tool_schemas_are_stable_and_merchant_independent():
    a = flow_for(Account("clinic", business_name="A"), DIRECTION_INBOUND)
    b = flow_for(Account("clinic", business_name="B", currency="GBP"), DIRECTION_INBOUND)
    assert a is b and a.slot_properties() == b.slot_properties()
