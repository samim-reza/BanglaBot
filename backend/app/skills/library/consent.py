"""The caller's approval of the booking terms — in the read-back, or as its own yes/no question."""

from __future__ import annotations

import hashlib
from datetime import timezone
from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import CONFIRMED, SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.base import FieldSpec, L

MODES = (
    ("in_readback", L("Read with the summary", "সারসংক্ষেপের সাথে পড়া হবে")),
    ("separate", L("Ask as its own question", "আলাদা প্রশ্ন হিসেবে")),
)


class ConsentSkill(Skill):
    key = "consent"
    kind = "gate"
    label = L2("Approval", "সম্মতি")
    description = L2("Reads your terms and gets the caller's yes.", "আপনার শর্ত পড়ে কলারের সম্মতি নেয়।")
    default_enabled = False
    options = (FieldSpec("mode", L("How to ask", "কীভাবে জিজ্ঞেস করবে"), "select", options=MODES, default="in_readback"),)
    defaults = {"mode": "in_readback"}
    slots = (SlotSpec("consent", "true = the caller agrees to the terms just read, false = they don't. Only after the terms were read.", {"type": "boolean"}),)
    gated = ("consent",)
    yes_no = {"consent": "consent"}
    lines = (
        line("terms", "Please note: cancellations need 24 hours' notice.", "দয়া করে মনে রাখবেন: বাতিল করতে ২৪ ঘণ্টা আগে জানাতে হবে।", label="Your terms", static=True),
        line("ask", "Do you agree?", "আপনি কি রাজি?", label="Ask to agree (own question)", static=True),
        line("declined", "No problem. Without that I can't complete the booking, but our team can help you. Goodbye.", "ঠিক আছে। এটা ছাড়া বুকিং করা যাচ্ছে না, আমাদের টিম সাহায্য করবে। ভালো থাকবেন।", label="If they don't agree", static=True),
    )
    goal = "Read the terms and get a clear yes or no."

    def required(self, b: BoundSkill) -> tuple[str, ...]:
        return ("consent",) if b.opt("mode") == "separate" else ()

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("consent",)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if b.opt("mode") != "separate":
            return None
        return "consent" if slots.get("consent") is not True else None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        if slots.get("consent") is False:
            return Instruction("consent", b.text("declined", language), verbatim=True, end_call=True)
        return f"{b.text('terms', language)} {b.text('ask', language)}"

    def readback_part(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("terms", language) if b.opt("mode") != "separate" else ""

    def commit_details(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        agreed = slots.get("consent") is True or (b.opt("mode") != "separate" and slots.get(CONFIRMED) is True)
        if not agreed:
            return {}
        text = b.text("terms", "en")
        return {
            "consent": {
                "at": ctx.now.astimezone(timezone.utc).isoformat() if ctx.now else "",
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        }

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("terms", language), b.text("declined", language)]


__all__ = ["ConsentSkill"]
