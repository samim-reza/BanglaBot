"""The contact number — skipped when caller ID already gave one."""

from __future__ import annotations

from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.reception import PHONE_HINT, caller_phone, clean_phone
from app.voice.languages import phrase


class PhoneSkill(Skill):
    key = "phone"
    label = L2("Phone number", "ফোন নম্বর")
    description = L2("Asked only when the caller's number is hidden.", "কলারের নম্বর না দেখালে জিজ্ঞেস করা হয়।")
    slots = (SlotSpec("phone", f"Mobile number to reach the caller, digits only. {PHONE_HINT}"),)
    lines = (line("phone", "What's the best mobile number to reach you?", "আপনার মোবাইল নম্বরটা বলবেন?", label="Ask for the number", static=True),)
    long_answer = frozenset({"phone"})
    volunteerable = frozenset({"phone"})
    goal = "Get a mobile number to reach them."

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return None if caller_phone(slots, ctx) else "phone"

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        phone = clean_phone(fields.get("phone"))
        if not phone:
            fields.pop("phone", None)
            return fields, Instruction("phone", phrase("phone_invalid", language), verbatim=True)
        fields["phone"] = phone
        return fields, None

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("phone", language), phrase("phone_invalid", language)]


__all__ = ["PhoneSkill"]
