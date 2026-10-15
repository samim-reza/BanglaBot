"""The home-service call pipelines: which skills, in what order, per branch.

Inbound::

    greet → (intent: book unless they ask otherwise)
          ─ book ───────▶ service → problem → name → address (+ service area) → day / arrival window
          │                → phone → payment* → approval* → read-back → booked → text
          ├ reschedule ─▶ find booking → day / window → read-back → moved
          └ cancel ─────▶ find booking → read-back → cancelled
    (* off by default. Gas smell / sparks / fire are emergencies at any point.)

Outbound visit confirmation: identity → is the time OK? ─ no → another day? → day → read-back.

A booking is an *arrival window*, never an exact minute; capacity per window = teams.
"""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.pipeline.blueprint import Blueprint, Branch
from app.skills.library.consent import ConsentSkill
from app.skills.library.emergency import EmergencySkill
from app.skills.library.greet import FarewellSkill, GreetSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.lines import L2, line
from app.skills.library.lookup import LookupSkill
from app.skills.library.notify import NotifySkill
from app.skills.library.payment import PaymentSkill
from app.skills.library.phone import PhoneSkill
from app.skills.library.schedule import ScheduleSkill
from app.verticals.home_service.catalog import KIND_BOOKING, chosen_service, record_service, record_when, service_availability
from app.verticals.home_service.flow import HomeServiceFlow
from app.verticals.home_service.skills import (
    AddressSkill,
    AnotherDaySkill,
    BookFirstIntentSkill,
    HomeConfirmSkill,
    ProblemSkill,
    ServiceSkill,
    TimeOkSkill,
)

RED_FLAGS = ("gas smell or leak", "sparks or burning smell from wiring", "fire", "electric shock", "water flooding near electrics")

EMERGENCY_LINES = (
    line(
        "emergency",
        "This could be dangerous. Get everyone to a safe place now, don't touch any switch or flame, and call {emergency} right away.",
        "এটা বিপজ্জনক হতে পারে। এখনই সবাই নিরাপদ জায়গায় সরে যান, কোনো সুইচ বা আগুন জ্বালাবেন না, আর সাথে সাথে {emergency} নম্বরে ফোন করুন।",
        label="Emergency line",
        variables=("emergency",),
        required=("emergency",),
    ),
)

CUSTOMER_FIELDS = (
    IntakeField("customer_name", L2("Name", "নাম"), L2("May I have your name?", "আপনার নামটা বলবেন?"), required=True, hint="The caller's name."),
    IntakeField("email", L2("Email", "ইমেইল"), L2("What email should we send the details to?", "কোন ইমেইলে বিস্তারিত পাঠাব?"), type="email", on=False),
    IntakeField("access", L2("Access notes", "প্রবেশের তথ্য"), L2("Anything the technician should know to get in — a gate code or parking?", "টেকনিশিয়ানের ঢোকার জন্য কিছু জানার আছে — গেট কোড বা পার্কিং?"), on=False, long_answer=True),
)

SCHEDULE_SLOTS = (
    SlotSpec("date", "Visit date as YYYY-MM-DD. Convert a day the caller names ('tomorrow', 'Friday') with the calendar in the facts."),
    SlotSpec("time_window", "Preferred arrival window.", {"type": "string", "enum": ["morning", "afternoon", "evening"]}),
)


def _describe(record: Any, ctx: CallContext, language: str) -> str:
    item = record_service(record, ctx)
    return f"{record_when(record, ctx, language)} {item.name if item else ''}".strip()


def _visit_charge(slots: dict[str, Any], ctx: CallContext) -> Any:
    service = chosen_service(slots, ctx)
    return service.get("visit_charge") if service else 0


def schedule_skill(needed) -> ScheduleSkill:  # noqa: ANN001
    return ScheduleSkill(
        availability=lambda slots, ctx: service_availability(ctx),
        needed=needed,
        pref_key="",
        window_key="time_window",
        slots=SCHEDULE_SLOTS,
        lines=(
            line("ask", "Which day suits you?", "কোন দিন আসলে সুবিধা হয়?", label="Ask for a day", static=True),
            line("ask_short", "Which day suits you?", "কোন দিন আসলে সুবিধা হয়?", label="Ask again", static=True),
        ),
        goal="Which day (and a preferred arrival window if they say one).",
    )


def emergency_skill() -> EmergencySkill:
    return EmergencySkill(red_flags=RED_FLAGS, lines=EMERGENCY_LINES)


def inbound_skills() -> dict[str, Any]:
    skills = [
        GreetSkill(lines=(*GreetSkill.lines[:2], line("opening_question", "What service do you need today?", "কী ধরনের সার্ভিস প্রয়োজন, বলুন?", label="First question", variables=("business",), static=True))),
        FarewellSkill(),
        HomeConfirmSkill(),
        BookFirstIntentSkill(
            {"book": "a new technician visit", "reschedule": "move an existing booking", "cancel": "cancel an existing booking"},
            lines=(
                line("intent", "Would you like to book a technician, or change or cancel a booking?", "আপনি কি টেকনিশিয়ান বুক করতে চান, নাকি কোনো বুকিং বদলাতে বা বাতিল করতে চান?", label="Ask what they need", static=True),
                line("branch_off", "Sorry, I can't do that over the phone, but our team can help you.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, আমাদের টিম সাহায্য করবে।", label="Not offered by phone", static=True),
            ),
            goal="Book a visit unless the caller asks to move or cancel an existing booking.",
        ),
        emergency_skill(),
        ServiceSkill(),
        ProblemSkill(),
        IntakeSkill(CUSTOMER_FIELDS, label=L2("Customer details", "কাস্টমারের তথ্য"), goal="The caller's name."),
        AddressSkill(),
        schedule_skill(lambda slots, ctx: slots.get("intent", "book") in ("book", "reschedule")),
        PhoneSkill(lines=(line("phone", "What's your mobile number?", "আপনার মোবাইল নম্বরটা বলবেন?", label="Ask for the number", static=True),), goal="A mobile number."),
        PaymentSkill(amount=_visit_charge, label=L2("Call-out charge", "ভিজিটিং চার্জ")),
        ConsentSkill(
            lines=(
                line("terms", "Please note: the call-out charge applies even if you decide not to go ahead with the repair.", "দয়া করে মনে রাখবেন: কাজ না করালেও ভিজিটিং চার্জ দিতে হবে।", label="Your terms", static=True),
                line("ask", "Is that okay?", "ঠিক আছে?", label="Ask to agree (own question)", static=True),
                line("declined", "No problem. Without that I can't book the visit, but our team can help you. Goodbye.", "ঠিক আছে। এটা ছাড়া বুকিং করা যাচ্ছে না, আমাদের টিম সাহায্য করবে। ভালো থাকবেন।", label="If they don't agree", static=True),
            ),
        ),
        LookupSkill(
            record_kind=KIND_BOOKING,
            describe=_describe,
            slot="booking",
            which_stage="which_booking",
            none_stage="no_booking_found",
            noun="booking",
        ),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


BOOK_BRANCH = Branch(
    "book",
    ("service", "problem", "intake", "address", "schedule", "phone", "payment", "consent"),
    label=L2("Book a visit", "ভিজিট বুকিং"),
    movable=(frozenset({"problem", "intake", "address", "schedule", "phone"}),),
    before={"problem": frozenset({"service"}), "payment": frozenset({"service", "schedule"}), "consent": frozenset({"payment"})},
    toggleable=False,
)


def inbound_blueprint() -> Blueprint:
    return Blueprint(
        key="home_service.inbound",
        vertical="home_service",
        direction="inbound",
        skills=inbound_skills(),
        prelude=("intent",),
        router_slot="intent",
        branches={
            "book": BOOK_BRANCH,
            "reschedule": Branch("reschedule", ("lookup", "schedule"), label=L2("Move a booking", "বুকিং বদল")),
            "cancel": Branch("cancel", ("lookup",), label=L2("Cancel a booking", "বুকিং বাতিল")),
        },
        default_branch="book",
        globals=("emergency",),
        effects=("notify",),
        line_skills=("greet", "farewell", "confirm"),
        flow_cls=HomeServiceFlow,
    )


def outbound_blueprint() -> Blueprint:
    skills = [
        FarewellSkill(),
        HomeConfirmSkill(),
        TimeOkSkill(),
        AnotherDaySkill(),
        schedule_skill(lambda slots, ctx: slots.get("wants_new_time") is True),
        emergency_skill(),
        NotifySkill(),
    ]
    return Blueprint(
        key="home_service.outbound",
        vertical="home_service",
        direction="outbound",
        skills={skill.key: skill for skill in skills},
        branches={"confirm_visit": Branch("confirm_visit", ("time_ok", "new_time", "schedule"), label=L2("Visit confirmation", "ভিজিট কনফার্মেশন"), toggleable=False)},
        default_branch="confirm_visit",
        globals=("emergency",),
        effects=("notify",),
        line_skills=("farewell", "confirm"),
        flow_cls=HomeServiceFlow,
    )


INBOUND = inbound_blueprint()
OUTBOUND = outbound_blueprint()
BLUEPRINTS = {"inbound": INBOUND, "outbound": OUTBOUND}

__all__ = ["BLUEPRINTS", "CUSTOMER_FIELDS", "EMERGENCY_LINES", "INBOUND", "OUTBOUND", "RED_FLAGS", "inbound_skills"]
