"""Reception-only skills: help the caller (answer or take the request), and the read-back / closing wording."""

from __future__ import annotations

from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill, lang_pick
from app.skills.library.lines import L2, line

STAGE_HELP = "help"

_GUIDANCE = {
    "bn": "কলারের প্রশ্নের উত্তর দিন শুধু ব্যবসার তথ্য থেকে। যা জানা নেই বা কর্মীর দরকার (অর্ডারের অবস্থা, অভিযোগ), সেটা message-এ সেভ করুন।",
    "en": "Answer the caller from the business facts only. Anything you cannot answer or that needs staff (order status, complaints) — save it as message.",
}


class HelpSkill(Skill):
    """Answers from the facts (the model, in its own words); a request staff must handle becomes the message."""

    key = "help"
    label = L2("Questions and requests", "প্রশ্ন ও অনুরোধ")
    description = L2("Answers from your business information; anything else is taken as a message.", "ব্যবসার তথ্য থেকে উত্তর দেয়; বাকিটা বার্তা হিসেবে নেয়।")
    toggleable = False
    slots = (
        SlotSpec(
            "message",
            "What the caller needs a team member to follow up on, in a short sentence in their words "
            "(order status, complaint, request). Only when you cannot fully answer it yourself.",
        ),
    )
    long_answer = frozenset({STAGE_HELP})
    volunteerable = frozenset({"message"})
    stage_slots = {STAGE_HELP: ("message",)}
    goal = "Help the caller. Answer questions only from the business facts. When they need staff to follow up, save message."

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return (STAGE_HELP,)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return None if slots.get("message") else STAGE_HELP

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction:
        return Instruction(STAGE_HELP, lang_pick(_GUIDANCE, language))


class ReceptionConfirmSkill(Skill):
    """Holds the read-back and closing wording (editable); the flow assembles them."""

    key = "confirm"
    kind = "line"
    toggleable = False
    label = L2("Read-back and closing", "পড়ে শোনানো ও সমাপ্তি")
    description = L2("What is read back before the message is passed on, and what is said after.", "বার্তা জমার আগে যা পড়ে শোনানো হয় ও পরে যা বলা হয়।")
    lines = (
        line(
            "readback",
            "So your name is {name}, and your message is: {message}. A team member will call you on {phone} — is that right?",
            "তাহলে আপনার নাম {name}, আর আপনার বার্তা: {message}। আমাদের প্রতিনিধি {phone} নম্বরে ফোন করবেন — ঠিক আছে?",
            label="Read-back (number given)",
            variables=("name", "message", "phone"),
        ),
        line(
            "readback_own_number",
            "So your name is {name}, and your message is: {message}. A team member will call you back on this number — is that right?",
            "তাহলে আপনার নাম {name}, আর আপনার বার্তা: {message}। আমাদের প্রতিনিধি এই নম্বরেই আপনাকে ফোন করবেন — ঠিক আছে?",
            label="Read-back (caller's own number)",
            variables=("name", "message"),
        ),
        line(
            "closing_lead",
            "Thank you. One of our team will get in touch with you shortly.",
            "ধন্যবাদ। আমাদের একজন প্রতিনিধি শীঘ্রই আপনার সাথে যোগাযোগ করবেন।",
            label="After taking the message",
            static=True,
        ),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("closing_lead", language)]


__all__ = ["STAGE_HELP", "HelpSkill", "ReceptionConfirmSkill"]
