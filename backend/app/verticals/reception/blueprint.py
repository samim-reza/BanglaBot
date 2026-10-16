"""The reception pipeline (inbound, one branch)::

    greet → help (answer from the facts, or take the request) → caller's name → phone* → read-back → message
    (* skipped when caller ID gives the number)
"""

from __future__ import annotations

from app.pipeline.blueprint import Blueprint, Branch
from app.skills.library.greet import FarewellSkill, GreetSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.lines import L, line
from app.skills.library.notify import NotifySkill
from app.skills.library.phone import PhoneSkill
from app.verticals.reception.flow import ReceptionPipelineFlow
from app.verticals.reception.skills import HelpSkill, ReceptionConfirmSkill

CALLER_FIELDS = (
    IntakeField("caller_name", L("Name"), L("May I have your name, please?"), required=True, hint="As the caller said it."),
    IntakeField("email", L("Email"), L("What email can we reach you on?"), type="email", on=False),
    IntakeField("order_ref", L("Order number"), L("Do you have an order number?"), on=False),
)


def reception_skills() -> dict:
    skills = [
        GreetSkill(),
        # The closing line already thanks the caller.
        FarewellSkill(lines=(line("farewell", "Goodbye.", label="Goodbye", variables=("business",), static=True),)),
        ReceptionConfirmSkill(),
        HelpSkill(),
        IntakeSkill(CALLER_FIELDS, label=L("Caller details"), goal="Get the caller's name."),
        PhoneSkill(goal="Get a mobile number to call back."),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


def reception_blueprint(vertical: str) -> Blueprint:
    """The inbound reception pipeline for ``vertical`` (flow key ``<vertical>.inbound``)."""
    return Blueprint(
        key=f"{vertical}.inbound",
        vertical=vertical,
        direction="inbound",
        skills=reception_skills(),
        branches={
            "message": Branch(
                "message",
                ("help", "intake", "phone"),
                label=L("Message for the team"),
                movable=(frozenset({"intake", "phone"}),),
                before={"intake": frozenset({"help"}), "phone": frozenset({"help"})},
                toggleable=False,
            )
        },
        default_branch="message",
        effects=("notify",),
        line_skills=("greet", "farewell", "confirm"),
        flow_cls=ReceptionPipelineFlow,
    )


__all__ = ["CALLER_FIELDS", "reception_blueprint", "reception_skills"]
