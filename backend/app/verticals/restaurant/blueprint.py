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
from app.skills.library.lines import L2, line
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
            line("intent", "Would you like to place an order, or book a table?", "অর্ডার করতে চান, নাকি টেবিল বুক করতে চান?", label="Ask what they need", static=True),
            line("branch_off", "Sorry, I can't do that over the phone, but our team can help.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, আমাদের টিম সাহায্য করবে।", label="Not offered by phone", static=True),
        ),
        goal=(
            "Find out what they want: order food, book a table, check an order, or leave a message (answer menu questions from the facts). "
            "If they name any dish or drink, call update_cart with all of them (that starts the order) — not save_details."
        ),
    )


def name_skill(key: str, question: tuple[str, str], label: tuple[str, str], extra: tuple[IntakeField, ...] = ()) -> IntakeSkill:
    fields = (IntakeField("customer_name", L2("Name", "নাম"), L2(*question), required=True, long_answer=True), *extra)
    skill = IntakeSkill(fields, key=key, label=L2(*label), goal="Get their name.")
    skill.name_key = "customer_name"  # the name is a record column, not an intake detail
    return skill


def order_payment() -> PaymentSkill:
    return PaymentSkill(
        amount=_order_total,
        default_enabled=True,
        label=L2("Payment", "পেমেন্ট"),
        description=L2("Pay on pickup / delivery, by a texted link, or the caller's choice.", "পিকআপ/ডেলিভারিতে, এসএমএস লিংকে, বা কলারের পছন্দে।"),
        lines=(
            line("ask", "Would you like to pay online now with a link we text you, or pay when you get your order?", "এখনই এসএমএস লিংকে অনলাইনে পেমেন্ট করবেন, নাকি অর্ডার হাতে পেয়ে?", label="Ask how to pay", variables=("amount",)),
            line("readback_venue", "You'll pay when you get your order.", "অর্ডার হাতে পেয়ে পেমেন্ট করবেন।", label="Read-back (on pickup / delivery)", variables=("amount",)),
            line("readback_online", "We'll text you a payment link.", "পেমেন্টের লিংক এসএমএস করে পাঠাব।", label="Read-back (online)", variables=("amount",)),
            line("readback_required", "We'll text you a payment link; the order goes to the kitchen once it's paid.", "পেমেন্টের লিংক এসএমএস করব; পেমেন্ট হলেই অর্ডার কিচেনে যাবে।", label="Read-back (online required)", variables=("amount", "hold")),
            line("closing_online", "Please pay using the link in your texts.", "এসএমএস-এর লিংক থেকে পেমেন্টটা করে নেবেন।", label="Closing (online)", static=True),
        ),
        goal="Pay online now (texted link) or when they get the order?",
    )


def deposit_skill() -> PaymentSkill:
    return PaymentSkill(
        "deposit",
        amount=lambda slots, ctx: 0,
        label=L2("Deposit", "অগ্রিম"),
        description=L2("Take a deposit to hold the table (set the amount).", "টেবিল ধরে রাখতে অগ্রিম (অঙ্ক দিন)।"),
        defaults={"mode": "online_required", "amount_source": "deposit", "hold_minutes": 30},
        lines=(
            line("ask", "To hold the table we take a {amount} deposit. Would you like to pay it online now, or when you arrive?", "টেবিল ধরে রাখতে {amount} অগ্রিম নিই। এখনই অনলাইনে দেবেন, নাকি এসে?", label="Ask how to pay", variables=("amount",)),
            line("readback_venue", "The {amount} deposit is paid when you arrive.", "{amount} অগ্রিম এসে দেবেন।", label="Read-back (on arrival)", variables=("amount",)),
            line("readback_online", "We'll text you a link for the {amount} deposit.", "{amount} অগ্রিমের লিংক এসএমএস করব।", label="Read-back (online)", variables=("amount",)),
            line("readback_required", "We'll text you a link for the {amount} deposit; we hold the table for {hold} minutes until it's paid.", "{amount} অগ্রিমের লিংক এসএমএস করব; পেমেন্টের জন্য টেবিল {hold} মিনিট ধরে রাখব।", label="Read-back (online required)", variables=("amount", "hold")),
            line("closing_online", "Please pay the deposit using the link in your texts.", "এসএমএস-এর লিংক থেকে অগ্রিমটা দিয়ে দেবেন।", label="Closing (online)", static=True),
        ),
    )


def table_policy() -> ConsentSkill:
    return ConsentSkill(
        label=L2("Table policy", "টেবিলের নিয়ম"),
        lines=(
            line("terms", "Please note: we hold the table for 15 minutes after the booking time.", "দয়া করে মনে রাখবেন: বুকিংয়ের সময়ের পর টেবিল ১৫ মিনিট ধরে রাখা হয়।", label="Your terms", static=True),
            line("ask", "Is that okay?", "ঠিক আছে?", label="Ask to agree (own question)", static=True),
            line("declined", "No problem. Without that I can't book the table, but our team can help you. Goodbye.", "ঠিক আছে। এটা ছাড়া টেবিল বুক করা যাচ্ছে না, আমাদের টিম সাহায্য করবে। ভালো থাকবেন।", label="If they don't agree", static=True),
        ),
    )


def table_schedule() -> ScheduleSkill:
    return ScheduleSkill(
        availability=table_availability,
        needed=lambda slots, ctx: slots.get("intent") == "reservation",
        label=L2("Day and time", "দিন ও সময়"),
        lines=(
            line("ask", "We take reservations {schedule}. What day and time would you like?", "আমরা {schedule} রিজার্ভেশন নিই। কোন দিন, কয়টায় আসতে চান?", label="Ask for a day", variables=("who", "schedule")),
            line("ask_short", "What day and time would you like?", "কোন দিন, কয়টায় আসতে চান?", label="Ask again", static=True),
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
        name_skill("customer", ("May I have your name?", "আপনার নামটা বলবেন?"), ("Name", "নাম")),
        PhoneSkill(),
        OrderTimeSkill(),
        UpsellSkill(),
        order_payment(),
        PartySizeSkill(),
        table_schedule(),
        name_skill(
            "guest",
            ("What name should I put the reservation under?", "কার নামে রিজার্ভেশন দেব?"),
            ("Guest details", "অতিথির তথ্য"),
            (IntakeField("occasion", L2("Occasion", "উপলক্ষ"), L2("Is it for a special occasion?", "কোনো বিশেষ উপলক্ষ আছে?"), on=False),),
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
    label=L2("Food order", "খাবার অর্ডার"),
    movable=(frozenset({"address", "customer", "phone", "order_time"}),),
    before={"address": frozenset({"fulfillment"}), "upsell": frozenset({"cart", "fulfillment"}), "payment": frozenset({"cart", "fulfillment"})},
)
RESERVATION_BRANCH = Branch(
    "reservation",
    ("party_size", "schedule", "guest", "phone", "deposit", "consent"),
    label=L2("Table booking", "টেবিল বুকিং"),
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
        "status": Branch("status", ("status",), label=L2("Order status", "অর্ডারের অবস্থা"), tail=TAIL_NONE),
        "message": Branch("message", ("message", "customer", "phone"), label=L2("Message for the team", "টিমের জন্য বার্তা"), toggleable=False),
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
