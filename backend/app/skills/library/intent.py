"""The router: why the caller called — picks the branch (book, reschedule, cancel, order …)."""

from __future__ import annotations

from typing import Any, Mapping

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line


class IntentSkill(Skill):
    key = "intent"
    kind = "router"
    toggleable = False
    label = L2("Reason for calling", "কল করার কারণ")
    description = L2("Works out what the caller wants and routes the call.", "কলার কী চান বুঝে কলটি সঠিক ধাপে নেয়।")
    volunteerable = frozenset({"intent"})
    lines = (
        line("intent", "How can I help you today?", "আমি কীভাবে সাহায্য করতে পারি?", label="Ask what they need", static=True),
        line("branch_off", "Sorry, I can't help with that over the phone, but our team can.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, তবে আমাদের টিম সাহায্য করবে।", label="Not offered by phone", static=True),
    )

    def __init__(self, choices: Mapping[str, str], **overrides: Any) -> None:
        """``choices``: branch key → when to pick it (shown to the model)."""
        super().__init__(**overrides)
        self.choices = dict(choices)
        meaning = "; ".join(f"{key} = {text}" for key, text in self.choices.items())
        self.slots = (
            SlotSpec(
                "intent",
                f"What the caller wants, once they say it ({meaning}). Not for a question. Update it if they change their mind.",
                {"type": "string", "enum": list(self.choices)},
                directions=("inbound",),
            ),
        )
        self.goal = self.goal or "Find out what the caller wants (answer questions from the facts first)."

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        wanted = str(fields.get("intent") or "")
        offered = tuple(b.opt("_branches", tuple(self.choices)))
        if wanted and wanted not in offered:
            fields.pop("intent", None)
            return fields, Instruction("intent", b.text("branch_off", language), verbatim=True)
        return fields, None

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("intent", language), b.text("branch_off", language)]


__all__ = ["IntentSkill"]
