"""The restaurant's call pipeline: which skills, in what order, per branch.

Inbound::

    greet → intent ─ order ────────▶ items → pickup/delivery → address* → name → phone → when → upsell° → payment → read-back
                   ├ reservation ──▶ party size → day & time → guest → phone → deposit° → table policy° → read-back
                   ├ status ───────▶ latest order by phone → status line → anything else?
                   └ message ──────▶ message → name → phone → read-back        (also: groups over the maximum)
    (* delivery only · ° off by default. The order's items can be named or changed at any step.)
"""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.pipeline.blueprint import TAIL_NONE, Blueprint, Branch
from app.skills.library.consent import ConsentSkill
from app.skills.library.greet import FarewellSkill, GreetSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.intent import IntentSkill
from app.skills.library.lines import L, line
from app.skills.library.message import MessageSkill
from app.skills.library.notify import NotifySkill
from app.skills.library.payment import PaymentSkill
from app.skills.library.phone import PhoneSkill
from app.skills.library.schedule import ScheduleSkill
from app.verticals.restaurant.cart import totals
from app.verticals.restaurant.cart_skill import CartSkill
from app.verticals.restaurant.config import conf
from app.verticals.restaurant.confirm import RestaurantConfirmSkill
from app.verticals.restaurant.flow import RestaurantFlow
from app.verticals.restaurant.hours import table_availability
from app.verticals.restaurant.order_skills import AddressSkill, FulfillmentSkill, OrderTimeSkill, UpsellSkill
from app.verticals.restaurant.table_skills import PartySizeSkill, StatusSkill


def _order_total(slots: dict[str, Any], ctx: CallContext) -> float:
    return totals(slots.get("cart") or [], str(slots.get("fulfillment") or ""), conf(ctx)).total


def intent_skill() -> IntentSkill:
    return IntentSkill(
        {
            "order": "food for pickup or delivery",
            "reservation": "book a table",
            "status": "an order they already placed",
            "message": "anything for the team: a large group, catering, a complaint",
        },
        lines=(
            line("intent", "Would you like to place an order, or book a table?", label="Ask what they need", static=True),
            line("branch_off", "Sorry, I can't do that over the phone, but our team can help.", label="Not offered by phone", static=True),
        ),
        goal=(
            "Find out what they want: order food, book a table, check an order, or leave a message (answer menu questions from the facts). "
            "If they name any dish or drink, call update_cart with all of them (that starts the order) — not save_details."
        ),
    )


def name_skill(key: str, question: str, label: str, extra: tuple[IntakeField, ...] = ()) -> IntakeSkill:
    fields = (IntakeField("customer_name", L("Name"), L(question), required=True, long_answer=True), *extra)
    skill = IntakeSkill(fields, key=key, label=L(label), goal="Get their name.")
    skill.name_key = "customer_name"  # the name is a record column, not an intake detail
    return skill


def order_payment() -> PaymentSkill:
    return PaymentSkill(
        amount=_order_total,
        default_enabled=True,
        label=L("Payment"),
        description=L("Pay on pickup / delivery, by a texted link, or the caller's choice."),
        lines=(
            line("ask", "Would you like to pay online now with a link we text you, or pay when you get your order?", label="Ask how to pay", variables=("amount",)),
            line("readback_venue", "You'll pay when you get your order.", label="Read-back (on pickup / delivery)", variables=("amount",)),
            line("readback_online", "We'll text you a payment link.", label="Read-back (online)", variables=("amount",)),
            line("readback_required", "We'll text you a payment link; the order goes to the kitchen once it's paid.", label="Read-back (online required)", variables=("amount", "hold")),
            line("closing_online", "Please pay using the link in your texts.", label="Closing (online)", static=True),
        ),
        goal="Pay online now (texted link) or when they get the order?",
    )


def deposit_skill() -> PaymentSkill:
    return PaymentSkill(
        "deposit",
        amount=lambda slots, ctx: 0,
        label=L("Deposit"),
        description=L("Take a deposit to hold the table (set the amount)."),
        defaults={"mode": "online_required", "amount_source": "deposit", "hold_minutes": 30},
        lines=(
            line("ask", "To hold the table we take a {amount} deposit. Would you like to pay it online now, or when you arrive?", label="Ask how to pay", variables=("amount",)),
            line("readback_venue", "The {amount} deposit is paid when you arrive.", label="Read-back (on arrival)", variables=("amount",)),
            line("readback_online", "We'll text you a link for the {amount} deposit.", label="Read-back (online)", variables=("amount",)),
            line("readback_required", "We'll text you a link for the {amount} deposit; we hold the table for {hold} minutes until it's paid.", label="Read-back (online required)", variables=("amount", "hold")),
            line("closing_online", "Please pay the deposit using the link in your texts.", label="Closing (online)", static=True),
        ),
    )


def table_policy() -> ConsentSkill:
    return ConsentSkill(
        label=L("Table policy"),
        lines=(
            line("terms", "Please note: we hold the table for 15 minutes after the booking time.", label="Your terms", static=True),
            line("ask", "Is that okay?", label="Ask to agree (own question)", static=True),
            line("declined", "No problem. Without that I can't book the table, but our team can help you. Goodbye.", label="If they don't agree", static=True),
        ),
    )


def table_schedule() -> ScheduleSkill:
    return ScheduleSkill(
        availability=table_availability,
        needed=lambda slots, ctx: slots.get("intent") == "reservation",
        label=L("Day and time"),
        lines=(
            line("ask", "We take reservations {schedule}. What day and time would you like?", label="Ask for a day", variables=("who", "schedule")),
            line("ask_short", "What day and time would you like?", label="Ask again", static=True),
        ),
        goal="Get the day (and time) they want the table.",
    )


def inbound_skills() -> dict[str, Any]:
    skills = [
        GreetSkill(),
        FarewellSkill(),
        RestaurantConfirmSkill(),
        intent_skill(),
        CartSkill(),
        FulfillmentSkill(),
        AddressSkill(),
        name_skill("customer", "May I have your name?", "Name"),
        PhoneSkill(),
        OrderTimeSkill(),
        UpsellSkill(),
        order_payment(),
        PartySizeSkill(),
        table_schedule(),
        name_skill(
            "guest",
            "What name should I put the reservation under?",
            "Guest details",
            (IntakeField("occasion", L("Occasion"), L("Is it for a special occasion?"), on=False),),
        ),
        deposit_skill(),
        table_policy(),
        StatusSkill(),
        MessageSkill(),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


ORDER_BRANCH = Branch(
    "order",
    ("cart", "fulfillment", "address", "customer", "phone", "order_time", "upsell", "payment"),
    label=L("Food order"),
    movable=(frozenset({"address", "customer", "phone", "order_time"}),),
    before={"address": frozenset({"fulfillment"}), "upsell": frozenset({"cart", "fulfillment"}), "payment": frozenset({"cart", "fulfillment"})},
)
RESERVATION_BRANCH = Branch(
    "reservation",
    ("party_size", "schedule", "guest", "phone", "deposit", "consent"),
    label=L("Table booking"),
    movable=(frozenset({"guest", "phone"}),),
    before={"schedule": frozenset({"party_size"}), "deposit": frozenset({"schedule"}), "consent": frozenset({"deposit"})},
)

INBOUND = Blueprint(
    key="restaurant.inbound",
    vertical="restaurant",
    direction="inbound",
    skills=inbound_skills(),
    prelude=("intent",),
    router_slot="intent",
    branches={
        "order": ORDER_BRANCH,
        "reservation": RESERVATION_BRANCH,
        "status": Branch("status", ("status",), label=L("Order status"), tail=TAIL_NONE),
        "message": Branch("message", ("message", "customer", "phone"), label=L("Message for the team"), toggleable=False),
    },
    default_branch="order",
    # The cart is also global: food named before the intent (or at a later step) still lands in the order.
    globals=("cart",),
    effects=("notify",),
    line_skills=("greet", "farewell", "confirm"),
    flow_cls=RestaurantFlow,
)
BLUEPRINTS = {"inbound": INBOUND}

__all__ = ["BLUEPRINTS", "INBOUND", "ORDER_BRANCH", "RESERVATION_BRANCH", "inbound_skills"]
