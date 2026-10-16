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
from app.skills.library.lines import L, line
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
    IntakeField("customer_name", L("Name"), L("May I have your name?"), required=True, hint="The caller's name."),
    IntakeField("email", L("Email"), L("What email should we send the details to?"), type="email", on=False),
    IntakeField("notes", L("Notes for the stylist"), L("Anything we should know before your visit?"), on=False, long_answer=True),
)


def _describe(record: Any, ctx: CallContext, language: str) -> str:
    start = record.scheduled_at.astimezone(ctx.now.tzinfo)
    service, person = record_service(record, ctx), record_staff(record, ctx)
    what = service.name if service else ""
    if person is not None:
        what = f"{what} with {person.name}"
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
                line("intent", "Would you like to book an appointment, or change or cancel one?", label="Ask what they need", static=True),
                line("branch_off", "Sorry, I can't do that over the phone, but our team can help you.", label="Not offered by phone", static=True),
            ),
            goal="Find out whether they want to book, move or cancel (answer questions from the facts).",
        ),
        SalonServiceSkill(),
        StaffSkill(),
        SalonScheduleSkill(
            availability=booking_availability,
            needed=lambda slots, ctx: slots.get("intent") in ("book", "reschedule"),
            lines=(
                line("ask", "{who} works {schedule}. Which day would you like?", label="Ask for a day", variables=("who", "schedule")),
                line("ask_any", "Which day would you like to come in?", label="Ask for a day (anyone)", static=True),
                line("ask_short", "Which day would you like?", label="Ask again", static=True),
            ),
            goal="Get the day they want (and a preferred time if they mention one).",
        ),
        IntakeSkill(CLIENT_FIELDS, label=L("Client details"), goal="Get the client's name."),
        PhoneSkill(),
        PaymentSkill(
            amount=_price,
            label=L("Deposit"),
            defaults={"mode": "online_required", "amount_source": "deposit", "hold_minutes": 30},
        ),
        ConsentSkill(
            lines=(
                line("terms", "Please note: we need 24 hours' notice to cancel or move a booking.", label="Your cancellation policy", static=True),
                line("ask", "Is that okay?", label="Ask to agree (own question)", static=True),
                line("declined", "No problem. Without that I can't book it, but our team can help you. Goodbye.", label="If they don't agree", static=True),
            ),
            label=L("Cancellation policy"),
        ),
        LookupSkill(record_kind=KIND_BOOKING, describe=_describe, slot="booking", which_stage="which_booking", none_stage="no_booking_found", noun="booking"),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


BOOK_BRANCH = Branch(
    "book",
    ("service", "staff", "schedule", "intake", "phone", "payment", "consent"),
    label=L("New booking"),
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
        "reschedule": Branch("reschedule", ("lookup", "schedule"), label=L("Move a booking")),
        "cancel": Branch("cancel", ("lookup",), label=L("Cancel a booking")),
    },
    default_branch="book",
    effects=("notify",),
    line_skills=("greet", "farewell", "confirm"),
    flow_cls=SalonFlow,
)
BLUEPRINTS = {"inbound": INBOUND}

__all__ = ["BLUEPRINTS", "BOOK_BRANCH", "CLIENT_FIELDS", "INBOUND", "salon_skills"]
