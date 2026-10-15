"""The custom engine's call pipeline — the owner builds the intake from their own questions.

Inbound::

    greet → intent ─ book ─────▶ what → day & time → details → phone → payment° → approval° → read-back
                   ├ inquiry ──▶ details → phone → read-back                     (a lead for the team)
                   └ message ──▶ message → details → phone → read-back
    (° off by default. "Details" = the name plus the owner's own custom questions.)
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
from app.skills.library.message import MessageSkill
from app.skills.library.notify import NotifySkill
from app.skills.library.payment import PaymentSkill
from app.skills.library.phone import PhoneSkill
from app.skills.library.schedule import ScheduleSkill
from app.verticals.custom.catalog import availability, chosen
from app.verticals.custom.flow import CustomFlow
from app.verticals.custom.skills import CustomConfirmSkill, ResourceSkill


def _availability(slots: dict[str, Any], ctx: CallContext):  # noqa: ANN202
    return availability(chosen(slots, ctx), ctx)


def _price(slots: dict[str, Any], ctx: CallContext) -> Any:
    item = chosen(slots, ctx)
    return item.get("price") if item else 0


def _who(slots: dict[str, Any], ctx: CallContext, language: str) -> str:
    item = chosen(slots, ctx)
    return item.name if item else ""


def inbound_skills() -> dict[str, Any]:
    intake = IntakeSkill(
        (IntakeField("customer_name", L2("Name", "নাম"), L2("May I have your name?", "আপনার নামটা বলবেন?"), required=True, long_answer=True),),
        label=L2("Details", "তথ্য"),
        description=L2("Their name plus the questions you add.", "নাম ও আপনার যোগ করা প্রশ্ন।"),
        goal="Get the caller's details.",
    )
    intake.name_key = "customer_name"  # the name is a record column, not an intake detail
    skills = [
        GreetSkill(),
        FarewellSkill(),
        CustomConfirmSkill(),
        IntentSkill(
            {"book": "book something from the list", "inquiry": "have the team get back to them about something", "message": "leave a message for the team"},
            lines=(
                line("intent", "How can I help you today?", "আমি কীভাবে সাহায্য করতে পারি?", label="Ask what they need", static=True),
                line("branch_off", "Sorry, I can't do that over the phone, but our team can help.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, আমাদের টিম সাহায্য করবে।", label="Not offered by phone", static=True),
            ),
        ),
        ResourceSkill(),
        ScheduleSkill(
            availability=_availability,
            who=_who,
            needed=lambda slots, ctx: slots.get("intent") == "book",
            lines=(
                line("ask", "{who} is available {schedule}. Which day would you like?", "{who} পাওয়া যায় {schedule}। কোন দিন চান?", label="Ask for a day", variables=("who", "schedule")),
                line("ask_short", "Which day would you like?", "কোন দিন চান?", label="Ask again", static=True),
            ),
        ),
        intake,
        PhoneSkill(),
        PaymentSkill(amount=_price),
        ConsentSkill(),
        MessageSkill(),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


INBOUND = Blueprint(
    key="custom.inbound",
    vertical="custom",
    direction="inbound",
    skills=inbound_skills(),
    prelude=("intent",),
    router_slot="intent",
    branches={
        "book": Branch(
            "book",
            ("resource", "schedule", "intake", "phone", "payment", "consent"),
            label=L2("Booking", "বুকিং"),
            movable=(frozenset({"schedule", "intake", "phone"}),),
            before={"schedule": frozenset({"resource"}), "payment": frozenset({"resource", "schedule"}), "consent": frozenset({"payment"})},
        ),
        "inquiry": Branch("inquiry", ("intake", "phone"), label=L2("Inquiry", "জিজ্ঞাসা")),
        "message": Branch("message", ("message", "intake", "phone"), label=L2("Message", "বার্তা"), toggleable=False),
    },
    default_branch="book",
    effects=("notify",),
    line_skills=("greet", "farewell", "confirm"),
    flow_cls=CustomFlow,
)
BLUEPRINTS = {"inbound": INBOUND}

__all__ = ["BLUEPRINTS", "INBOUND", "inbound_skills"]
