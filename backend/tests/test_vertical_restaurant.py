"""The restaurant engine driven through the real tools + runtime with scripted model calls (no model,
no database): the cart tool, menu matching, totals, pickup vs delivery, tables, status, large groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest

from app.flows import hearing
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.scheduling import slot_key
from app.flows.timefmt import business_tz
from app.verticals import flow_for, get_vertical
from app.verticals.restaurant.match import best_match
from app.verticals.restaurant.menu import parse_modifiers
from app.voice.tools import CallTools, NullCallStore

NY = business_tz("America/New_York")
#: Friday 2 October 2026, 6 pm in New York (open 11:00–22:00).
NOW = datetime(2026, 10, 2, 18, 0, tzinfo=NY)
PIZZA = "Size*: Small 0 | Medium +2 | Large +4; Extras+: Cheese +1 | Bacon +2"


@dataclass
class Account:
    vertical: str = "restaurant"
    business_name: str = "Tony's"
    language: str = "en"
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"
    custom_greeting: str = ""
    support_phone: str = ""
    knowledge: str = ""
    vertical_config: dict = field(default_factory=lambda: {"delivery_fee": 4, "free_delivery_over": 40, "tax_rate": 8, "minimum_order": 15})
    voice_persona: str = "female"
    agent_flow: dict = field(default_factory=dict)
    id: str = "m1"


@dataclass
class Record:
    id: str
    customer_name: str
    customer_phone: str
    kind: str = "order"
    scheduled_at: datetime | None = None
    items_summary: str = ""
    details: dict = field(default_factory=dict)
    status: str = "confirmed"


MENU = [
    CatalogEntry("m-pep", "I1", "menu_item", "Pepperoni Pizza", {"category": "Pizza", "price": 14, "modifiers": PIZZA, "allergens": ["gluten", "dairy"]}),
    CatalogEntry("m-mar", "I2", "menu_item", "Margherita Pizza", {"category": "Pizza", "price": 12, "modifiers": "Size*: Small | Medium +2 | Large +4"}),
    CatalogEntry("m-gb", "I3", "menu_item", "Garlic Bread", {"category": "Sides", "price": 5}),
    CatalogEntry("m-coke", "I4", "menu_item", "Coca-Cola", {"category": "Drinks", "price": 2.5, "aliases": ["coke"]}),
    CatalogEntry("m-tira", "I5", "menu_item", "Tiramisu", {"category": "Dessert", "price": 7, "available": False}),
]


def _call(caller: str = "+16175550100", config: dict | None = None, agent_flow: dict | None = None, **kwargs: Any) -> tuple[CallTools, FlowRuntime, NullCallStore]:
    merchant = Account(agent_flow=agent_flow or {})
    if config is not None:
        merchant.vertical_config = config
    ctx = CallContext(merchant=merchant, catalog=list(MENU), direction=DIRECTION_INBOUND, now=NOW, caller_number=caller, **kwargs)
    runtime = FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en")
    store = NullCallStore(taken=kwargs.pop("taken", None))
    return CallTools(runtime, store), runtime, store


def _spoken(items: tuple[dict, ...]) -> str:
    """What a caller would say for these cart lines (the cart only keeps modifiers the caller said)."""
    parts = []
    for item in items:
        mods = item.get("modifiers") or []
        parts.append(" ".join([str(item.get("qty", "")), str(item.get("item", "")), *(mods if isinstance(mods, list) else [mods])]))
    return "I'd like " + " and ".join(parts)


async def cart(tools: CallTools, *items: dict, text: str = "", **extra: Any):
    return await tools.execute("update_cart", {"items": list(items), **extra}, caller_text=text or _spoken(items) or "order")


# ---------------------------------------------------------------------------- menu + matching
def test_modifier_syntax_parses_groups_prices_and_flags():
    size, extras = parse_modifiers(PIZZA)
    assert size.name == "Size" and size.required and not size.multi
    assert [(o.label, o.price) for o in size.options] == [("Small", 0), ("Medium", 2), ("Large", 4)]
    assert extras.name == "Extras" and extras.multi and not extras.required
    assert parse_modifiers("Crust: Thin | Thick (+1.50); junk") [0].options[1].price == 1.5


def test_menu_matching_is_fuzzy_and_phonetic_but_not_loose():
    items = [(entry.name, [entry.name, *entry.data.get("aliases", [])]) for entry in MENU]
    assert best_match("peperoni", items).best == "Pepperoni Pizza"
    assert best_match("coke", items).best == "Coca-Cola"
    assert best_match("garlic toast", items).status == "suggest"
    assert best_match("pizza", items).status == "choose"
    assert best_match("sushi", items).status == "none"


# ---------------------------------------------------------------------------- the cart tool
@pytest.mark.asyncio
async def test_food_named_first_starts_the_order_and_the_cart_is_edited_by_the_tool():
    tools, runtime, _ = _call()
    result = await cart(tools, {"item": "pepperoni pizza", "qty": 2, "modifiers": ["large"]}, {"item": "garlic bread"}, fulfillment="delivery", text="two large pepperoni pizzas and a garlic bread for delivery")
    assert result.stop and result.say == "You have 2 Pepperoni Pizza (Large) and 1 Garlic Bread. Anything else?"
    assert runtime.slots["intent"] == "order" and runtime.slots["fulfillment"] == "delivery"
    line = runtime.slots["cart"][0]
    assert line["unit"] == 18 and line["qty"] == 2 and line["options"] == [{"group": "Size", "label": "Large", "price": 4.0}]
    # Change options (bacon), quantity, then remove the bread — all through the same tool.
    await cart(tools, {"item": "pepperoni", "action": "replace", "modifiers": ["bacon"]})
    assert runtime.slots["cart"][0]["unit"] == 20 and [o["label"] for o in runtime.slots["cart"][0]["options"]] == ["Large", "Bacon"]
    await cart(tools, {"item": "pepperoni pizza", "action": "set_qty", "qty": 3})
    result = await cart(tools, {"item": "garlic bread", "action": "remove"})
    assert [(l["name"], l["qty"]) for l in runtime.slots["cart"]] == [("Pepperoni Pizza", 3)]
    assert result.say == "You have 3 Pepperoni Pizza (Large, Bacon). Anything else?"


@pytest.mark.asyncio
async def test_required_choice_is_asked_and_a_near_miss_is_confirmed():
    tools, runtime, _ = _call()
    result = await cart(tools, {"item": "margherita"})
    assert result.say == "Which size would you like for the Margherita Pizza: Small, Medium or Large?"
    fast = runtime.flow.fast_fields(runtime.stage, "large", hearing.classify("large"), runtime.slots, runtime.ctx)
    assert fast == {"item_option": "Large"}
    result = await tools.execute("save_details", fast, caller_text="large")
    assert runtime.slots["cart"][0]["unit"] == 16 and not runtime.slots["cart"][0]["missing"]
    result = await cart(tools, {"item": "garlic toast"})
    assert result.say == "Did you mean the Garlic Bread?" and runtime.stage == "cart_pick"
    result = await tools.execute("save_details", {"pick_ok": True}, caller_text="yes")
    assert result.say == "You have 1 Margherita Pizza (Large) and 1 Garlic Bread. Anything else?"


@pytest.mark.asyncio
async def test_the_caller_finishing_the_order_skips_anything_else():
    # "… and a garlic bread, that's it": the tool's done flag passes the gate; a repeated entry is not doubled.
    tools, runtime, _ = _call()
    await tools.execute("save_details", {"intent": "order", "fulfillment": "delivery"}, caller_text="I'd like to order for delivery")
    result = await cart(tools, {"item": "pepperoni", "modifiers": ["large"], "qty": 2}, {"item": "pepperoni", "modifiers": ["large"]}, {"item": "garlic bread"}, done=True)
    assert [(l["name"], l["qty"]) for l in runtime.slots["cart"]] == [("Pepperoni Pizza", 2), ("Garlic Bread", 1)]
    assert runtime.slots["more_items"] is False and result.say == "What's the delivery address?"
    # Answering "anything else?" with the address means that's all too.
    tools, runtime, _ = _call()
    await cart(tools, {"item": "coke", "qty": 6}, fulfillment="delivery")
    result = await tools.execute("save_details", {"address": "9 Pier Road"}, caller_text="9 Pier Road")
    assert runtime.slots["more_items"] is False and result.say == "May I have your name?"


@pytest.mark.asyncio
async def test_an_item_waiting_for_a_choice_is_filled_not_duplicated():
    tools, runtime, _ = _call()
    await cart(tools, {"item": "margherita pizza", "qty": 2})
    result = await cart(tools, {"item": "margherita", "modifiers": ["medium"]})
    assert [(l["qty"], l["unit"], l["missing"]) for l in runtime.slots["cart"]] == [(2, 14, [])]
    assert result.say == "You have 2 Margherita Pizza (Medium). Anything else?"


@pytest.mark.asyncio
async def test_unavailable_and_unknown_items_are_refused_without_touching_the_cart():
    tools, runtime, _ = _call()
    await cart(tools, {"item": "coke"})
    result = await cart(tools, {"item": "tiramisu"}, {"item": "sushi"})
    assert "Sorry, we don't have sushi." in result.say and "Tiramisu isn't available today" in result.say
    assert [l["name"] for l in runtime.slots["cart"]] == ["Coca-Cola"]
    assert result.say.endswith("You have 1 Coca-Cola. Anything else?")


@pytest.mark.asyncio
async def test_cart_tool_is_refused_outside_an_order():
    tools, runtime, _ = _call()
    await tools.execute("save_details", {"intent": "reservation"}, caller_text="I'd like to book a table")
    result = await cart(tools, {"item": "pepperoni pizza"})
    assert result.payload["ok"] is False and result.payload["reason"] == "not_now"
    assert "cart" not in runtime.slots and runtime.stage == "party_size"


# ---------------------------------------------------------------------------- totals, pickup vs delivery
@pytest.mark.asyncio
async def test_delivery_read_back_has_fee_tax_and_total_and_free_delivery_over_the_threshold():
    tools, runtime, store = _call()
    await cart(tools, {"item": "pepperoni pizza", "modifiers": ["small"]}, {"item": "coke", "qty": 2}, fulfillment="delivery")
    await tools.execute("save_details", {"more_items": False}, caller_text="that's it")
    assert runtime.stage == "address"
    await tools.execute("save_details", {"address": "12 Main Street, Apt 4"}, caller_text="12 Main Street apartment 4")
    await tools.execute("save_details", {"customer_name": "Sam"}, caller_text="Sam")
    result = await tools.execute("save_details", {"order_time": "asap"}, caller_text="as soon as possible")
    # 14 + 2 × 2.50 = 19 food; 4 delivery; 8% tax on food = 1.52 → 24.52.
    assert result.say.startswith("So that's 1 Pepperoni Pizza (Small) and 2 Coca-Cola, for delivery to 12 Main Street, Apt 4, arriving in about 45 minutes.")
    assert "That's 19 dollars plus 4 dollars delivery and 1 dollars and 52 cents tax. Your total is 24 dollars and 52 cents." in result.say
    assert result.say.endswith("Is everything correct so I can confirm the order?")
    # A change at the read-back is confirmed and the summary is read again — now over 40: free delivery.
    result = await cart(tools, {"item": "pepperoni pizza", "modifiers": ["large"]}, {"item": "garlic bread"})
    assert result.say.startswith("Got it, I've added Pepperoni Pizza and Garlic Bread. So that's")
    # 19 + 18 + 5 = 42 food (free delivery over 40); 8% tax = 3.36 → 45.36.
    assert "Delivery is free." in result.say and "Your total is 45 dollars and 36 cents." in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "booked" and result.say.startswith("Your order is confirmed — it should arrive in about 45 minutes.")
    action = store.commits[0]["action"]
    assert action.fields["kind"] == "order" and action.fields["total_amount"] == 45.36 and action.fields["address"] == "12 Main Street, Apt 4"
    details = action.fields["details"]
    assert details["delivery_fee"] == 0 and details["tax"] == 3.36 and details["subtotal"] == 42 and details["fulfillment"] == "delivery"
    assert [item["line_total"] for item in details["items"]] == [14, 5, 18, 5]
    assert action.fields["scheduled_at"] == NOW + timedelta(minutes=45)


@pytest.mark.asyncio
async def test_pickup_skips_the_address_and_a_later_time_is_kept():
    tools, runtime, store = _call()
    await cart(tools, {"item": "garlic bread", "qty": 2})
    await tools.execute("save_details", {"more_items": False}, caller_text="no thanks")
    result = await tools.execute("save_details", {"fulfillment": "pickup"}, caller_text="pickup")
    assert runtime.stage == "customer_name" and result.say == "May I have your name?"
    await tools.execute("save_details", {"customer_name": "Ana"}, caller_text="Ana")
    result = await tools.execute("save_details", {"order_time": "19:30"}, caller_text="half past seven")
    assert "for pickup, today at 7:30 PM." in result.say and "delivery" not in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.say.startswith("Your order is confirmed — it'll be ready today at 7:30 PM.")
    fields = store.commits[0]["action"].fields
    assert fields["address"] == "" and fields["details"]["fulfillment"] == "pickup" and fields["total_amount"] == 10.8


async def _to_upsell(tools: CallTools) -> Any:
    await cart(tools, {"item": "pepperoni pizza", "modifiers": ["large"]}, {"item": "margherita", "modifiers": ["small"]}, {"item": "garlic bread"}, fulfillment="delivery")
    await tools.execute("save_details", {"more_items": False}, caller_text="that's all")
    await tools.execute("save_details", {"address": "5 Elm Road"}, caller_text="5 Elm Road")
    await tools.execute("save_details", {"customer_name": "Jo"}, caller_text="Jo")
    return await tools.execute("save_details", {"order_time": "asap"}, caller_text="asap")


@pytest.mark.asyncio
async def test_upsell_is_off_by_default_and_asked_once_when_on():
    tools, runtime, _ = _call()
    assert (await _to_upsell(tools)).say.startswith("So that's")  # off: straight to the read-back
    tools, runtime, _ = _call(agent_flow={"steps": {"upsell": {"enabled": True}}})
    result = await _to_upsell(tools)  # 35 of food, free delivery over 40
    assert result.say == "You're 5 dollars away from free delivery. Would you like to add anything?" and runtime.stage == "upsell"
    result = await tools.execute("save_details", {"upsell_ok": True}, caller_text="yes")
    assert result.say == "What else would you like?"
    await cart(tools, {"item": "coke", "qty": 2})
    result = await tools.execute("save_details", {"more_items": False}, caller_text="that's it")
    assert result.say.startswith("So that's") and "Delivery is free." in result.say
    tools, runtime, _ = _call(agent_flow={"steps": {"upsell": {"enabled": True, "options": {"mode": "item", "item": "Coca-Cola"}}}})
    result = await _to_upsell(tools)
    assert result.say == "Would you like to add Coca-Cola for 2 dollars and 50 cents?"
    result = await tools.execute("save_details", {"upsell_ok": True}, caller_text="sure")
    assert "1 Garlic Bread and 1 Coca-Cola" in result.say


@pytest.mark.asyncio
async def test_delivery_below_the_minimum_asks_to_add_or_pick_up():
    tools, runtime, _ = _call()
    await cart(tools, {"item": "coke"}, fulfillment="delivery")
    result = await tools.execute("save_details", {"more_items": False}, caller_text="that's all")
    assert runtime.stage == "fulfillment" and "minimum order of 15 dollars" in result.say


# ---------------------------------------------------------------------------- tables
@pytest.mark.asyncio
async def test_reservation_uses_covers_capacity_and_books_the_table():
    full = slot_key(None, datetime(2026, 10, 3, 19, 0, tzinfo=NY))
    tools, runtime, store = _call(booked={full: 10})  # 40 covers ÷ party of 4 = 10 tables: 7 PM is full
    result = await tools.execute(
        "save_details", {"intent": "reservation", "party_size": 4, "date": "2026-10-03", "time_pref": "19:00"}, caller_text="a table for four tomorrow at 7"
    )
    assert runtime.slots["slot"] == datetime(2026, 10, 3, 19, 30, tzinfo=NY).isoformat()
    assert result.say == "What name should I put the reservation under?"
    result = await tools.execute("save_details", {"customer_name": "Lee"}, caller_text="Lee")
    assert "So that's a table for 4 tomorrow at 7:30 PM, under Lee." in result.say and result.say.endswith("Shall I book it?")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.outcome == "booked" and "Your table is booked for tomorrow at 7:30 PM." in result.say
    action = store.commits[0]["action"]
    assert action.fields["kind"] == "booking" and action.fields["details"]["party_size"] == 4
    assert action.capacity == (None, datetime(2026, 10, 3, 19, 30, tzinfo=NY), 10)


@pytest.mark.asyncio
async def test_a_group_over_the_maximum_becomes_a_message_for_the_team():
    tools, runtime, store = _call()
    result = await tools.execute("save_details", {"intent": "reservation", "party_size": 14}, caller_text="a table for 14 people")
    assert runtime.slots["intent"] == "message" and runtime.stage == "customer_name"
    assert result.say == "For groups larger than 10, our team arranges it personally — I'll pass on your details. May I have your name?"
    result = await tools.execute("save_details", {"customer_name": "Priya"}, caller_text="Priya")
    assert "So I'll pass this on to our team: Table for 14 people. They'll call you back on this number." in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    action = store.commits[0]["action"]
    assert result.outcome == "lead" and action.fields["kind"] == "lead" and action.fields["details"]["party_size"] == 14


# ---------------------------------------------------------------------------- order status
@pytest.mark.asyncio
async def test_status_reads_the_callers_latest_order_then_offers_more_help():
    order = Record("o-1", "Sam", "+16175550100", scheduled_at=NOW + timedelta(minutes=25), items_summary="1× Pepperoni Pizza (Large)", details={"fulfillment": "delivery", "progress": "preparing"})
    tools, runtime, _ = _call(caller_records=[order])
    result = await tools.execute("save_details", {"intent": "status"}, caller_text="where is my order")
    assert result.say == "Your order of 1 Pepperoni Pizza (Large) is being prepared — it should arrive today at 6:25 PM. Is there anything else I can help with?"
    fast = runtime.flow.fast_fields(runtime.stage, "no", hearing.classify("no"), runtime.slots, runtime.ctx)
    await tools.execute("save_details", fast, caller_text="no")
    assert runtime.stage == "done"
    order.details["progress"] = "out_for_delivery"
    tools, runtime, _ = _call(caller_records=[order])
    result = await tools.execute("save_details", {"intent": "status"}, caller_text="status of my order")
    assert result.say.startswith("Your order is on its way.")


@pytest.mark.asyncio
async def test_status_without_an_order_offers_to_take_one():
    tools, runtime, _ = _call()
    result = await tools.execute("save_details", {"intent": "status"}, caller_text="where is my order")
    assert result.say == "I can't find a recent order for this number. Would you like to place one?"
    result = await tools.execute("save_details", {"order_instead": True}, caller_text="yes")
    assert runtime.slots["intent"] == "order" and result.say == "What would you like to order?"


def test_restaurant_vertical_declares_menu_and_settings():
    vertical = get_vertical("restaurant")
    spec = vertical.as_json()
    assert vertical.catalog_kind == "menu_item" and spec["configurable_flow"]
    assert {"modifiers", "allergens", "available", "aliases"} <= {f["key"] for f in spec["catalog_fields"]}
    assert {"tax_rate", "free_delivery_over", "covers_per_slot", "max_party_size"} <= {f["key"] for f in spec["config_fields"]}
