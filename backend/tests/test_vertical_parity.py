"""The ported verticals (home service, real estate, reception) on the skill pipeline say and write
what their legacy hand-written flows did: the same scripted calls run through both.
(Their original tests in test_verticals.py run unchanged on the pipeline too.)"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.flows import hearing
from app.flows.base import Flow
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.timefmt import business_tz
from app.pipeline.flow import PipelineFlow
from app.verticals import flow_for
from app.verticals.home_service import legacy as home_legacy
from app.verticals.real_estate import legacy as realty_legacy
from app.verticals.reception.legacy import ReceptionFlow
from app.voice.tools import CallTools, NullCallStore

NY = business_tz("America/New_York")
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=NY)  # Friday 8 pm
S = "save_details"

CATALOG = [
    CatalogEntry("s-ac", "S1", "service", "AC repair", {"category": "HVAC", "visit_charge": 89, "price_from": 120, "price_to": 450}),
    CatalogEntry("s-plumb", "S2", "service", "Plumbing", {"category": "Plumbing", "visit_charge": 79}),
    CatalogEntry("p-maple", "P1", "property", "3-bed family home, Maple Grove", {"listing_type": "sale", "property_type": "house", "location": "Maple Grove", "price": 485000}),
    CatalogEntry("p-condo", "P2", "property", "Modern 1-bed condo, Downtown", {"listing_type": "rent", "property_type": "flat", "location": "Downtown", "price": 2100}),
]


@dataclass
class Account:
    vertical: str
    language: str = "en"
    business_name: str = "Test Co"
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"
    custom_greeting: str = ""
    support_phone: str = ""
    knowledge: str = ""
    vertical_config: dict = field(default_factory=lambda: {"service_areas": ["Brooklyn", "Queens"], "teams": 2})
    id: str = "m1"


@dataclass
class Record:
    id: str = "r1"
    customer_name: str = "Maria"
    customer_phone: str = "+17185550133"
    kind: str = "booking"
    catalog_item_id: str | None = "s-ac"
    scheduled_at: datetime | None = datetime(2026, 10, 5, 9, 0, tzinfo=NY)
    details: dict = field(default_factory=lambda: {"time_window": "morning", "intent": "buy", "property_type": "house", "location": "Maple Grove"})
    address: str = "315 Atlantic Ave"


HOME_IN = [
    (S, {"service": "S1"}, "my AC"), (S, {"problem": "leaking"}, "it's leaking"), (S, {"customer_name": "Mark"}, "Mark"),
    (S, {"area": "Hoboken", "address": "1 River St"}, "Hoboken"), (S, {"address": "42 Bergen St", "area": "Brooklyn"}, "42 Bergen St Brooklyn"),
    (S, {"date": "2026-10-03", "time_window": "evening"}, "tomorrow evening"), (S, {"confirmed": True}, "yes"),
]
HOME_OUT = [(S, {"identity_confirmed": True}, "yes speaking"), (S, {"time_ok": False}, "no it doesn't"), (S, {"wants_new_time": True}, "yes"),
            (S, {"date": "2026-10-06"}, "Tuesday"), (S, {"confirmed": True}, "yes")]
HOME_LEAD = [(S, {"service": "S2", "problem": "sink blocked", "customer_name": "Sam"}, "blocked sink, Sam"), ("end_call", {"reason": "bye"}, "never mind, bye")]
BUY = [(S, {"intent": "buy"}, "buy"), (S, {"caller_name": "Chris"}, "Chris"), (S, {"property_type": "house"}, "a house"), (S, {"location": "Maple Grove"}, "Maple Grove"),
       (S, {"budget": "up to 500k", "budget_max": 500000}, "500k"), (S, {"timeline": "now"}, "now"), (S, {"wants_visit": True, "property": "P1"}, "yes"),
       (S, {"visit_date": "2026-10-05", "visit_time_pref": "15:00"}, "Monday at 3"), (S, {"confirmed": True}, "yes")]
RENT_NO_VISIT = [(S, {"intent": "rent", "caller_name": "Kim", "property_type": "flat"}, "rent a flat, Kim"), (S, {"location": "Downtown"}, "Downtown"),
                 (S, {"budget": "2k"}, "2k"), (S, {"timeline": "1-3 months"}, "soon"), (S, {"wants_visit": False}, "no")]
# Sellers are now asked their timeline too (the legacy flow never asked): given up front, both flows skip it.
SELL = [(S, {"intent": "sell", "property_type": "land", "caller_name": "Rita", "location": "Oak Hills", "size": "one acre", "timeline": "1-3 months"}, "sell land"), (S, {"asking_price": "250k"}, "250k"), (S, {"confirmed": True}, "yes")]
FOLLOW_UP = [(S, {"identity_confirmed": True}, "yes speaking"), (S, {"still_interested": True}, "yes still interested"), (S, {"budget": "500k"}, "500k"),
             (S, {"timeline": "later"}, "later"), (S, {"wants_visit": False}, "no")]
NOT_INTERESTED = [(S, {"identity_confirmed": True}, "yes speaking"), (S, {"still_interested": False}, "no I'm not interested")]
MESSAGE = [(S, {"message": "Where is my order?"}, "where is my order"), (S, {"caller_name": "Emily"}, "Emily"), (S, {"confirmed": True}, "yes")]
MESSAGE_NO_ID = [(S, {"message": "Refund please", "caller_name": "Bo"}, "refund, Bo"), (S, {"phone": "+1 415 555 0199"}, "plus one four one five"), (S, {"confirmed": True}, "yes")]

CASES = {
    "home-inbound": ("home_service", DIRECTION_INBOUND, home_legacy.INBOUND, HOME_IN, "+17185550101"),
    "home-confirmation-moved": ("home_service", DIRECTION_OUTBOUND, home_legacy.OUTBOUND, HOME_OUT, ""),
    "home-out-of-area-lead": ("home_service", DIRECTION_INBOUND, home_legacy.INBOUND, HOME_LEAD, "+17185550101"),
    "realty-buyer-visit": ("real_estate", DIRECTION_INBOUND, realty_legacy.INBOUND, BUY, "+13055550110"),
    "realty-renter-no-visit": ("real_estate", DIRECTION_INBOUND, realty_legacy.INBOUND, RENT_NO_VISIT, "+13055550110"),
    "realty-seller": ("real_estate", DIRECTION_INBOUND, realty_legacy.INBOUND, SELL, "+13055550110"),
    "realty-follow-up": ("real_estate", DIRECTION_OUTBOUND, realty_legacy.OUTBOUND, FOLLOW_UP, ""),
    "realty-not-interested": ("real_estate", DIRECTION_OUTBOUND, realty_legacy.OUTBOUND, NOT_INTERESTED, ""),
    "reception-message": ("ecommerce", DIRECTION_INBOUND, ReceptionFlow(vertical="ecommerce"), MESSAGE, "+14155550123"),
    "reception-no-caller-id": ("ecommerce", DIRECTION_INBOUND, ReceptionFlow(vertical="ecommerce"), MESSAGE_NO_ID, ""),
}
#: Stage names that changed on the pipeline (reception's name step is the intake field's key).
STAGE_ALIAS = {"name": "caller_name"}


async def _run(flow: Flow, vertical: str, direction: str, script: list, caller: str, language: str) -> tuple[list, list, list]:
    record = Record() if direction == DIRECTION_OUTBOUND else None
    ctx = CallContext(merchant=Account(vertical, language=language), catalog=list(CATALOG), direction=direction, now=NOW, caller_number=caller, record=record)
    runtime = FlowRuntime(flow, ctx, language=language)
    store = NullCallStore()
    tools = CallTools(runtime, store)
    stages, lines = [runtime.stage], [flow.opening(ctx, language)]
    for name, fields, text in script:
        result = await tools.execute(name, dict(fields), caller_text=text)
        # The pipeline keeps the call open after a write ("anything else?"); the legacy flow was done there.
        stages.append("done" if runtime.slots.get("_after") else STAGE_ALIAS.get(runtime.stage, runtime.stage))
        lines.append(result.say or ("" if result.outcome else result.payload.get("instruction", "")))
    commits = []
    for commit in store.commits:
        action = commit["action"]
        details = {k: v for k, v in (action.fields.get("details") or {}).items() if k not in ("idem", "intake", "payment")}
        commits.append((action.outcome, action.status, action.record_id, action.capacity, {k: v for k, v in action.fields.items() if k != "details"}, details))
    return stages, lines, commits


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(CASES))
async def test_pipeline_port_says_and_writes_what_the_legacy_flow_did(case: str):
    vertical, direction, legacy_flow, script, caller = CASES[case]
    pipeline_flow = flow_for(Account(vertical), direction)
    assert isinstance(pipeline_flow, PipelineFlow) and not isinstance(legacy_flow, PipelineFlow)
    new_stages, new_lines, new_commits = await _run(pipeline_flow, vertical, direction, script, caller, "en")
    old_stages, old_lines, old_commits = await _run(legacy_flow, vertical, direction, script, caller, "en")
    assert new_stages == old_stages
    assert new_commits == old_commits
    # Every question and read-back is word for word the same; only the closing's goodbye moved to the editable farewell.
    assert new_lines[:-1] == old_lines[:-1]
    assert bool(new_lines[-1]) == bool(old_lines[-1])


@pytest.mark.asyncio
async def test_home_service_callers_can_now_move_or_cancel_a_booking():
    booking = Record(customer_phone="+17185550101", details={"time_window": "morning"})
    ctx = CallContext(merchant=Account("home_service"), catalog=list(CATALOG), direction=DIRECTION_INBOUND, now=NOW, caller_number="+17185550101", caller_records=[booking])
    runtime = FlowRuntime(flow_for(ctx.merchant, DIRECTION_INBOUND), ctx, language="en")
    store = NullCallStore()
    tools = CallTools(runtime, store)
    # The router starts on "book": a caller with a job is never asked what they want.
    assert runtime.slots["intent"] == "book" and runtime.stage == "service"
    result = await tools.execute(S, {"intent": "cancel"}, caller_text="I need to cancel my AC visit")
    assert result.say == "Shall I cancel the AC repair visit on Monday, October 5 between 9 AM and 12 PM?"
    fields: dict[str, Any] = runtime.flow.fast_fields(runtime.stage, "Yes, cancel it", hearing.classify("Yes, cancel it"), runtime.slots, ctx) or {}
    result = await tools.execute(S, fields, caller_text="Yes, cancel it")
    assert result.outcome == "cancelled" and store.commits[0]["action"].record_id == "r1"
