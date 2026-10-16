"""The router: why the caller called — picks the branch (book, reschedule, cancel, order …)."""

from __future__ import annotations

from typing import Any, Mapping

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L, line
from app.voice.languages import phrase


class IntentSkill(Skill):
    key = "intent"
    kind = "router"
    toggleable = False
    label = L("Reason for calling")
    description = L("Works out what the caller wants and routes the call.")
    volunteerable = frozenset({"intent"})
    lines = (
        line("intent", "How can I help you today?", label="Ask what they need", static=True),
        line("branch_off", "Sorry, I can't help with that over the phone, but our team can.", label="Not offered by phone", static=True),
        line("anything_else", "Is there anything else I can help you with?", label="After a booking", static=True),
    )
    #: Goal while the call stays open after a booking ("anything else?").
    after_goal = (
        "The caller's request is done and saved. Wait for their answer to 'anything else?'. To change or cancel what was "
        "just booked, save intent as the reschedule/cancel option; for another, separate booking save the matching intent; "
        "answer questions from the facts. If they're finished, call end_call."
    )

    def __init__(self, choices: Mapping[str, str], **overrides: Any) -> None:
        """``choices``: branch key → when to pick it (shown to the model)."""
        super().__init__(**overrides)
        if self.line_spec("anything_else") is None:
            # Verticals that bring their own router lines still get the after-booking question.
            self.lines = (*self.lines, *(spec for spec in IntentSkill.lines if spec.key == "anything_else"))
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

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        if slots.get("_after"):
            return b.text("anything_else", language) or phrase("anything_else", language)
        return super().line(b, stage, slots, ctx, language)

    def brief(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext) -> str:
        return self.after_goal if slots.get("_after") else self.goal

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("intent", language), b.text("branch_off", language), b.text("anything_else", language)]


__all__ = ["IntentSkill"]
