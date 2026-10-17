"""Closure dates through every booking engine (the real tools + runtime, scripted model calls):
a closed day is refused with the reason and the next open day, "first available" skips it,
and a commit into a closure is refused."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.flows.base import CommitAction
from app.flows.closures import blocked_commit
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.timefmt import business_tz
from app.verticals import flow_for
from app.voice.tools import CallTools, NullCallStore
from tests.test_vertical_custom import RESOURCES
from tests.test_vertical_restaurant import MENU
from tests.test_vertical_salon import CATALOG as SALON
from tests.test_verticals import DOCTORS, LISTINGS, SERVICES

NY = business_tz("America/New_York")
NOW = datetime(2026, 11, 20, 20, 0, tzinfo=NY)  # Friday 8 pm
THANKSGIVING = {"start": "2026-11-26", "label": "Thanksgiving"}
CLOSED_THANKSGIVING = "We're closed on Thursday, November 26 for Thanksgiving — the next open day is Friday, November 27."
VET = [CatalogEntry("vet-lee", "D1", "doctor", "Dr. Hannah Lee", {"days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 20})]
DENTAL = [CatalogEntry("den-park", "D1", "doctor", "Dr. Emily Park", {"days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 30})]


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
    id: str = "m-close"


def _call(vertical: str, catalog: list[CatalogEntry], closures: list[dict], *, now: datetime = NOW, **config: Any):
    merchant = Account(vertical, vertical_config={**config, "closures": closures})
    ctx = CallContext(merchant=merchant, catalog=list(catalog), direction=DIRECTION_INBOUND, now=now, caller_number="+16175550100")
    runtime = FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en")
    store = NullCallStore()
    return CallTools(runtime, store), runtime, store


async def say(tools: CallTools, text: str = "", **fields: Any) -> str:
    return (await tools.execute("save_details", fields, caller_text=text or "ok")).say


# ---------------------------------------------------------------------------- clinic, dental, vet
@pytest.mark.asyncio
@pytest.mark.parametrize(("vertical", "catalog"), [("clinic", DOCTORS), ("dental", DENTAL), ("vet", VET)])
async def test_doctors_practices_refuse_the_holiday_and_offer_the_next_open_day(vertical: str, catalog: list[CatalogEntry]):
    tools, runtime, store = _call(vertical, catalog, [THANKSGIVING])
    line = await say(tools, "an appointment on Thanksgiving", intent="book", doctor="D1", date="2026-11-26")
    assert line.startswith(CLOSED_THANKSGIVING) and runtime.stage == "date" and "date" not in runtime.slots
    assert not store.commits


@pytest.mark.asyncio
async def test_clinic_ranges_a_doctors_leave_and_first_available_skip_closures():
    leave = {"start": "2026-11-23", "item_id": "doc-carter"}
    holidays = {"start": "2026-12-24", "end": "2026-12-26", "label": "Holidays"}
    tools, runtime, store = _call("clinic", DOCTORS, [THANKSGIVING, holidays, leave], booking_horizon_days=45)
    line = await say(tools, "Dr Mitchell on Christmas", intent="book", doctor="D1", date="2026-12-25")
    assert line.startswith("We're closed from Thursday, December 24 to Saturday, December 26 for Holidays — the next open day is Monday, December 28.")
    line = await say(tools, "Dr Carter on Monday", doctor="D2", date="2026-11-23")
    assert line.startswith("Dr. James Carter isn't available on Monday, November 23 — the next available day is Wednesday, November 25.")
    # "Whatever's first" lands on Carter's next day in, not his leave.
    await say(tools, "the earliest", date="earliest")
    assert runtime.slots["date"] == "2026-11-25"
    await say(tools, "Leo", patient_name="Leo")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "booked" and store.commits[0]["action"].fields["scheduled_at"].date().isoformat() == "2026-11-25"


@pytest.mark.asyncio
async def test_a_closure_added_mid_call_is_never_booked():
    tools, runtime, store = _call("clinic", DOCTORS, [])
    await say(tools, "Dr Mitchell Tuesday, Ana", intent="book", doctor="D1", date="2026-11-24", patient_name="Ana")
    assert runtime.stage == "confirm"
    runtime.ctx.merchant.vertical_config = {"closures": [{"start": "2026-11-24", "label": "Staff training"}]}
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert not store.commits and runtime.stage == "date"
    assert result.say.startswith("We're closed on Tuesday, November 24 for Staff training — the next open day is Wednesday, November 25.")


def test_commit_check_blocks_new_and_moved_times_but_not_an_unchanged_one():
    tools, runtime, _ = _call("clinic", DOCTORS, [THANKSGIVING, {"start": "2026-11-27", "item_id": "doc-carter"}])
    ctx = runtime.ctx
    holiday = datetime(2026, 11, 26, 10, 0, tzinfo=NY)
    friday = datetime(2026, 11, 27, 10, 0, tzinfo=NY)
    assert blocked_commit(CommitAction("booked", "confirmed", fields={"scheduled_at": holiday}), ctx).label == "Thanksgiving"
    assert blocked_commit(CommitAction("booked", "confirmed", fields={"scheduled_at": friday, "catalog_item_id": "doc-carter"}), ctx) is not None
    assert blocked_commit(CommitAction("booked", "confirmed", fields={"scheduled_at": friday, "catalog_item_id": "doc-mitchell"}), ctx) is None
    ctx.caller_records = [type("Rec", (), {"id": "a1", "scheduled_at": holiday})()]
    assert blocked_commit(CommitAction("rescheduled", "confirmed", record_id="a1", fields={"scheduled_at": holiday}), ctx) is None
    assert blocked_commit(CommitAction("confirmed", "confirmed", record_id="a1"), ctx) is None


# ---------------------------------------------------------------------------- salon, custom
@pytest.mark.asyncio
async def test_salon_closes_for_everyone_or_one_stylist():
    maya_off = {"start": "2026-11-24", "item_id": "st-maya"}
    tools, runtime, _ = _call("salon", SALON, [THANKSGIVING, maya_off])
    line = await say(tools, "a haircut with anyone on Thanksgiving, Ana", intent="book", service="S1", staff="anyone", date="2026-11-26", customer_name="Ana")
    assert line.startswith(CLOSED_THANKSGIVING)
    line = await say(tools, "with Maya on Tuesday", staff="Maya", date="2026-11-24")
    assert line.startswith("Maya isn't available on Tuesday, November 24 — the next available day is Wednesday, November 25.")
    line = await say(tools, "anyone then", staff="anyone", date="2026-11-24")
    assert "a Haircut with Leo, Tuesday, November 24" in line


@pytest.mark.asyncio
async def test_custom_resource_closure_names_the_resource():
    renovation = {"start": "2026-11-23", "end": "2026-11-24", "label": "Renovation", "item_id": "r-private"}
    tools, runtime, _ = _call("custom", RESOURCES, [renovation])
    await say(tools, "I'd like to book", intent="book")
    line = await say(tools, "private session Monday", resource="private session", date="2026-11-23")
    assert line.startswith("Private session isn't available from Monday, November 23 to Tuesday, November 24 for Renovation — the next available day is Wednesday, November 25.")


# ---------------------------------------------------------------------------- home service, real estate
@pytest.mark.asyncio
async def test_home_service_window_on_a_holiday_is_refused():
    tools, runtime, _ = _call("home_service", SERVICES, [THANKSGIVING], service_areas=["Brooklyn"])
    await say(tools, "AC leaking, Mark", service="S1", problem="AC leaking", customer_name="Mark")
    await say(tools, "42 Bergen St Brooklyn", address="42 Bergen St, Brooklyn", area="Brooklyn")
    line = await say(tools, "Thursday morning", date="2026-11-26", time_window="morning")
    assert line.startswith(CLOSED_THANKSGIVING) and runtime.stage == "date"


@pytest.mark.asyncio
async def test_real_estate_viewing_on_a_closed_day_is_refused():
    tools, runtime, _ = _call("real_estate", LISTINGS, [{"start": "2026-11-21", "label": "Open house prep"}])
    await say(tools, "buy a house, Chris", intent="buy", property_type="house", caller_name="Chris")
    await say(tools, "Maple Grove up to 500k", location="Maple Grove", budget="up to 500k", budget_max=500000)
    await say(tools, "in a month or two", timeline="1-3 months")
    await say(tools, "I'd like to see it", property="P1", wants_visit=True)
    line = await say(tools, "Saturday morning", visit_date="2026-11-21", visit_time_pref="morning")
    assert line.startswith("We're closed tomorrow for Open house prep — the next open day is Monday, November 23.")


# ---------------------------------------------------------------------------- restaurant
@pytest.mark.asyncio
async def test_restaurant_tables_on_a_holiday_are_refused():
    tools, runtime, _ = _call("restaurant", MENU, [THANKSGIVING])
    line = await say(tools, "a table for four on Thanksgiving at 7", intent="reservation", party_size=4, date="2026-11-26", time_pref="19:00")
    assert line.startswith(CLOSED_THANKSGIVING) and runtime.stage == "date"


@pytest.mark.asyncio
async def test_restaurant_orders_on_a_closed_day_wait_for_the_next_open_day():
    tools, runtime, store = _call("restaurant", MENU, [THANKSGIVING], now=datetime(2026, 11, 26, 18, 0, tzinfo=NY))
    await tools.execute("update_cart", {"items": [{"item": "garlic bread", "qty": 2}]}, caller_text="2 garlic bread")
    await say(tools, "no thanks", more_items=False)
    await say(tools, "pickup", fulfillment="pickup")
    closed_today = "We're closed today for Thanksgiving — the next open day is tomorrow, Friday. What time would you like it?"
    assert await say(tools, "Ana", customer_name="Ana") == closed_today
    assert await say(tools, "as soon as possible", order_time="asap") == closed_today
    assert await say(tools, "half seven tonight", order_time="19:30") == closed_today
    line = await say(tools, "tomorrow at 12:30", order_time="2026-11-27 12:30")
    assert "for pickup, tomorrow, Friday at 12:30 PM" in line and runtime.stage == "confirm"


@pytest.mark.asyncio
async def test_an_order_whose_day_closes_mid_call_is_not_committed():
    tools, runtime, store = _call("restaurant", MENU, [])
    await tools.execute("update_cart", {"items": [{"item": "garlic bread", "qty": 2}]}, caller_text="2 garlic bread")
    await say(tools, "no thanks", more_items=False)
    await say(tools, "pickup", fulfillment="pickup")
    await say(tools, "Ana", customer_name="Ana")
    await say(tools, "Monday at noon", order_time="2026-11-23 12:00")
    assert runtime.stage == "confirm"
    runtime.ctx.merchant.vertical_config = {"closures": [{"start": "2026-11-23", "label": "Inventory"}]}
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert not store.commits and runtime.stage == "order_time" and "order_time" not in runtime.slots
    assert result.say.startswith("We're closed on Monday, November 23 for Inventory.")



def test_home_service_window_already_under_way_is_read_as_before_its_end():
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.verticals.home_service.catalog import window_label

    ny = business_tz("America/New_York")
    ctx = SimpleNamespace(now=datetime(2026, 10, 19, 9, 30, tzinfo=ny))
    windows = {"time_windows": [{"key": "morning", "start": "08:00", "end": "12:00"}]}
    with patch("app.verticals.home_service.catalog.service_config", return_value=windows):
        assert window_label("morning", ctx, "en", datetime(2026, 10, 19, 8, 0, tzinfo=ny)) == "before 12 PM"
        assert window_label("morning", ctx, "en", datetime(2026, 10, 20, 8, 0, tzinfo=ny)) == "between 8 AM and 12 PM"
        assert window_label("morning", ctx, "en") == "between 8 AM and 12 PM"
