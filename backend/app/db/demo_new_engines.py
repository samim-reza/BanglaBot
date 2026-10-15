"""Demo accounts for the restaurant and custom engines (same rules as :mod:`app.db.demo_accounts`).

    restaurant / restaurant123     restaurant: orders + tables     (Luigi's Pizza Kitchen)
    custom / custom123             custom business (build your own) (Harbor Yoga Studio)
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.demo_accounts import US, _account, _items, _next_weekday
from app.flows.timefmt import business_tz
from app.models import Order, OrderStatus

_PIZZA = "Size*: Small 0 | Medium +3 | Large +6; Extras+: Extra cheese +1.5 | Mushrooms +1.5 | Pepperoni +2 | Fresh basil +0.5; Crust: Classic | Thin | Gluten-free +3"

#: The restaurant demo menu (also used by scripts/simulate.py).
RESTAURANT_MENU: list[tuple[str, dict[str, Any]]] = [
    ("Margherita Pizza", {"category": "Pizza", "price": 13, "modifiers": _PIZZA, "allergens": ["gluten", "dairy"],
                          "aliases": ["margarita", "cheese pizza", "plain pizza"], "available": True,
                          "description": "Tomato, mozzarella and basil."}),
    ("Pepperoni Pizza", {"category": "Pizza", "price": 15, "modifiers": _PIZZA, "allergens": ["gluten", "dairy", "pork"],
                         "aliases": ["pepperoni", "pep pizza"], "available": True}),
    ("Veggie Supreme Pizza", {"category": "Pizza", "price": 16, "modifiers": _PIZZA, "allergens": ["gluten", "dairy"],
                              "aliases": ["veggie pizza", "vegetable pizza"], "available": True,
                              "description": "Peppers, onions, mushrooms, olives."}),
    ("Chicken Wings", {"category": "Starters", "price": 11, "modifiers": "Sauce*: Buffalo | BBQ | Garlic parmesan; Size: 6 pieces | 12 pieces +9",
                       "allergens": ["dairy"], "aliases": ["wings", "buffalo wings"], "available": True}),
    ("Garlic Bread", {"category": "Starters", "price": 5.5, "modifiers": "Extras+: Cheese +1.5", "allergens": ["gluten", "dairy"], "available": True}),
    ("Caesar Salad", {"category": "Salads", "price": 9, "modifiers": "Add+: Grilled chicken +4 | Shrimp +6",
                      "allergens": ["dairy", "egg", "fish", "gluten"], "available": True}),
    ("Spaghetti Bolognese", {"category": "Pasta", "price": 14.5, "allergens": ["gluten"], "aliases": ["spaghetti", "bolognese"], "available": True}),
    ("Tiramisu", {"category": "Desserts", "price": 7, "allergens": ["dairy", "egg", "gluten"], "available": True}),
    ("Cannoli", {"category": "Desserts", "price": 6, "allergens": ["dairy", "gluten"], "available": False}),
    ("Coca-Cola", {"category": "Drinks", "price": 2.5, "modifiers": "Size: Can | 2 liter +2", "aliases": ["coke"], "available": True}),
    ("Sparkling Water", {"category": "Drinks", "price": 3, "aliases": ["san pellegrino", "fizzy water"], "available": True}),
]

#: What the custom demo account takes bookings for.
CUSTOM_RESOURCES: list[tuple[str, dict[str, Any]]] = [
    ("Private yoga session", {"description": "One-to-one, 60 minutes.", "days": ["mon", "tue", "wed", "thu", "fri"],
                              "start_time": "07:00", "end_time": "19:00", "slot_minutes": 60, "capacity": 1, "price": 80}),
    ("Evening group class", {"description": "All levels, mats provided.", "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
                             "start_time": "18:00", "end_time": "20:00", "slot_minutes": 60, "capacity": 12, "price": 20}),
    ("Studio rental", {"description": "The whole studio for workshops, 2 hours.", "days": ["sat", "sun"],
                       "start_time": "10:00", "end_time": "16:00", "slot_minutes": 120, "capacity": 1, "price": 150}),
]

#: The custom account's own intake questions (call-flow settings → details → custom fields).
CUSTOM_INTAKE = {
    "steps": {
        "intake": {
            "options": {
                "custom": [
                    {"key": "level", "label": "Experience level", "question": "Have you done yoga before — beginner, intermediate or advanced?",
                     "type": "choice", "choices": ["beginner", "intermediate", "advanced"], "required": True},
                    {"key": "injuries", "label": "Injuries", "question": "Any injuries our teacher should know about?", "type": "text"},
                ]
            }
        }
    }
}


async def seed_restaurant(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="restaurant",
        password="restaurant123",
        business_name="Luigi's Pizza Kitchen",
        owner_name="Luigi Romano",
        email="restaurant@example.com",
        phone="+12125550160",
        vertical="restaurant",
        vertical_config={
            "open_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open_time": "11:00", "close_time": "22:00",
            "delivery": True, "delivery_fee": 3.99, "free_delivery_over": 40, "minimum_order": 15, "tax_rate": 8.875,
            "prep_minutes": 20, "delivery_minutes": 45, "max_party_size": 10, "covers_per_slot": 40, "slot_minutes": 30,
        },
        knowledge=(
            "Luigi's Pizza Kitchen, 214 Mulberry Street, New York, NY 10012. We deliver within 3 miles. "
            "Gluten-free crust is made in a shared kitchen, so we can't guarantee no cross-contact. "
            "Street parking only. Kids eat free on Tuesdays with an adult entree."
        ),
        widget_settings={"title": "Luigi's Pizza Kitchen", "subtitle": "Order or book a table", "color": "#b91c1c"},
    )
    if merchant is None:
        return None
    session.add_all(_items(merchant, "menu_item", RESTAURANT_MENU))
    await session.flush()
    tz = business_tz(US["timezone"])
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).date()
    session.add_all(
        [
            Order(
                merchant_id=merchant.id, kind="order", customer_name="Chris Walker", customer_phone="+12125550142",
                address="88 Grand Street, Apt 5C, New York, NY 10013", items_summary="1× Pepperoni Pizza (Large), 1× Garlic Bread",
                total_amount=Decimal("30.47"), currency="USD", scheduled_at=now + timedelta(minutes=25),
                details={"type": "order", "fulfillment": "delivery", "order_time": "asap", "progress": "preparing",
                         "subtotal": 26.5, "delivery_fee": 3.99, "tax": 2.35, "total": 30.47},
                status=OrderStatus.confirmed,
            ),
            Order(
                merchant_id=merchant.id, kind="booking", customer_name="Nina Patel", customer_phone="+12125550177",
                scheduled_at=datetime.combine(tomorrow, time(19, 0), tzinfo=tz), items_summary="Table for 4",
                currency="USD", details={"type": "reservation", "party_size": 4}, status=OrderStatus.confirmed,
            ),
        ]
    )
    return merchant.username


async def seed_custom(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="custom",
        password="custom123",
        business_name="Harbor Yoga Studio",
        owner_name="Maya Lin",
        email="custom@example.com",
        phone="+16465550190",
        vertical="custom",
        vertical_config={"booking_horizon_days": 14, "lead_minutes": 60},
        agent_flow=CUSTOM_INTAKE,
        knowledge=(
            "Harbor Yoga Studio, 9 Pier Road, Brooklyn, NY 11201. Mats and towels provided. "
            "Arrive 10 minutes early for your first class. Cancellations up to 12 hours before are free."
        ),
        widget_settings={"title": "Harbor Yoga Studio", "subtitle": "Book a class", "color": "#0e7490"},
    )
    if merchant is None:
        return None
    resources = _items(merchant, "resource", CUSTOM_RESOURCES)
    session.add_all(resources)
    await session.flush()
    tz = business_tz(US["timezone"])
    day = _next_weekday(datetime.now(tz), {0, 1, 2, 3, 4})
    session.add(
        Order(
            merchant_id=merchant.id, kind="booking", customer_name="Jordan Kim", customer_phone="+16465550111",
            catalog_item_id=resources[0].id, scheduled_at=datetime.combine(day.date(), time(9, 0), tzinfo=tz),
            items_summary="Private yoga session", total_amount=Decimal("80"), currency="USD",
            details={"type": "booking", "resource": "Private yoga session"}, status=OrderStatus.confirmed,
        )
    )
    return merchant.username


__all__ = ["CUSTOM_INTAKE", "CUSTOM_RESOURCES", "RESTAURANT_MENU", "seed_custom", "seed_restaurant"]
