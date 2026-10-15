"""The salon & spa call pipeline (inbound)::

    greet → intent ─ book ───────▶ service → who ("anyone" is fine) → day (fits the service in their hours)
                   │                → name → phone* → deposit* → cancellation policy* → read-back → book → text
                   ├ reschedule ─▶ find booking → day → read-back → move
                   └ cancel ─────▶ find booking → read-back → cancel
    (* phone only when caller ID is hidden; deposit and policy are off by default.)
"""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.pipeline.blueprint import Blueprint, Branch
from app.skills.library.consent import ConsentSkill
from app.skills.library.greet import FarewellSkill, GreetSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.intent import IntentSkill
from app.skills.library.lines import L2, line
from app.skills.library.lookup import LookupSkill
from app.skills.library.notify import NotifySkill
from app.skills.library.payment import PaymentSkill
from app.skills.library.phone import PhoneSkill
from app.verticals.common import when_phrase
from app.verticals.salon.availability import booking_availability
from app.verticals.salon.catalog import KIND_BOOKING, chosen_service, price, record_service, record_staff
from app.verticals.salon.flow import SalonFlow
from app.verticals.salon.skills import SalonConfirmSkill, SalonScheduleSkill, SalonServiceSkill, StaffSkill

CLIENT_FIELDS = (
    IntakeField("customer_name", L2("Name", "নাম"), L2("May I have your name?", "আপনার নামটা বলবেন?"), required=True, hint="The caller's name."),
    IntakeField("email", L2("Email", "ইমেইল"), L2("What email should we send the details to?", "কোন ইমেইলে বিস্তারিত পাঠাব?"), type="email", on=False),
    IntakeField("notes", L2("Notes for the stylist", "স্টাইলিস্টের জন্য নোট"), L2("Anything we should know before your visit?", "আসার আগে আমাদের কিছু জানার আছে?"), on=False, long_answer=True),
)


def _describe(record: Any, ctx: CallContext, language: str) -> str:
    start = record.scheduled_at.astimezone(ctx.now.tzinfo)
    service, person = record_service(record, ctx), record_staff(record, ctx)
    what = service.name if service else ""
    if person is not None:
        what = f"{person.name} {what}" if language == "bn" else f"{what} with {person.name}"
    return f"{when_phrase(start, ctx, language, on=True)} {what}".strip()


def _price(slots: dict[str, Any], ctx: CallContext) -> Any:
    return price(chosen_service(slots, ctx))


def salon_skills() -> dict[str, Any]:
    skills = [
        GreetSkill(),
        FarewellSkill(),
        SalonConfirmSkill(),
        IntentSkill(
            {"book": "a new appointment", "reschedule": "move an existing booking", "cancel": "cancel an existing booking"},
            lines=(
                line("intent", "Would you like to book an appointment, or change or cancel one?", "আপনি কি নতুন অ্যাপয়েন্টমেন্ট নিতে চান, নাকি কোনোটা বদলাতে বা বাতিল করতে চান?", label="Ask what they need", static=True),
                line("branch_off", "Sorry, I can't do that over the phone, but our team can help you.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, আমাদের টিম সাহায্য করবে।", label="Not offered by phone", static=True),
            ),
            goal="Find out whether they want to book, move or cancel (answer questions from the facts).",
        ),
        SalonServiceSkill(),
        StaffSkill(),
        SalonScheduleSkill(
            availability=booking_availability,
            needed=lambda slots, ctx: slots.get("intent") in ("book", "reschedule"),
            lines=(
                line("ask", "{who} works {schedule}. Which day would you like?", "{who} {schedule} কাজ করেন। কোন দিন আসতে চান?", label="Ask for a day", variables=("who", "schedule")),
                line("ask_any", "Which day would you like to come in?", "কোন দিন আসতে চান?", label="Ask for a day (anyone)", static=True),
                line("ask_short", "Which day would you like?", "কোন দিন চান?", label="Ask again", static=True),
            ),
            goal="Get the day they want (and a preferred time if they mention one).",
        ),
        IntakeSkill(CLIENT_FIELDS, label=L2("Client details", "ক্লায়েন্টের তথ্য"), goal="Get the client's name."),
        PhoneSkill(),
        PaymentSkill(
            amount=_price,
            label=L2("Deposit", "অগ্রিম"),
            defaults={"mode": "online_required", "amount_source": "deposit", "hold_minutes": 30},
        ),
        ConsentSkill(
            lines=(
                line("terms", "Please note: we need 24 hours' notice to cancel or move a booking.", "দয়া করে মনে রাখবেন: বুকিং বাতিল বা বদলাতে ২৪ ঘণ্টা আগে জানাতে হবে।", label="Your cancellation policy", static=True),
                line("ask", "Is that okay?", "ঠিক আছে?", label="Ask to agree (own question)", static=True),
                line("declined", "No problem. Without that I can't book it, but our team can help you. Goodbye.", "ঠিক আছে। এটা ছাড়া বুকিং করা যাচ্ছে না, আমাদের টিম সাহায্য করবে। ভালো থাকবেন।", label="If they don't agree", static=True),
            ),
            label=L2("Cancellation policy", "বাতিলের নিয়ম"),
        ),
        LookupSkill(record_kind=KIND_BOOKING, describe=_describe, slot="booking", which_stage="which_booking", none_stage="no_booking_found", noun="booking"),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


BOOK_BRANCH = Branch(
    "book",
    ("service", "staff", "schedule", "intake", "phone", "payment", "consent"),
    label=L2("New booking", "নতুন বুকিং"),
    movable=(frozenset({"schedule", "intake", "phone"}),),
    before={"staff": frozenset({"service"}), "schedule": frozenset({"service", "staff"}), "payment": frozenset({"service", "schedule"}), "consent": frozenset({"payment"})},
    toggleable=False,
)

INBOUND = Blueprint(
    key="salon.inbound",
    vertical="salon",
    direction="inbound",
    skills=salon_skills(),
    prelude=("intent",),
    router_slot="intent",
    branches={
        "book": BOOK_BRANCH,
        "reschedule": Branch("reschedule", ("lookup", "schedule"), label=L2("Move a booking", "বুকিং বদল")),
        "cancel": Branch("cancel", ("lookup",), label=L2("Cancel a booking", "বুকিং বাতিল")),
    },
    default_branch="book",
    effects=("notify",),
    line_skills=("greet", "farewell", "confirm"),
    flow_cls=SalonFlow,
)
BLUEPRINTS = {"inbound": INBOUND}

__all__ = ["BLUEPRINTS", "BOOK_BRANCH", "CLIENT_FIELDS", "INBOUND", "salon_skills"]
