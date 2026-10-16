"""New or returning customer (patient) — answered from caller history when possible."""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill
from app.skills.library.choice import ChoiceSkill
from app.skills.library.lines import line
from app.verticals.base import FieldSpec, L


class CustomerTypeSkill(ChoiceSkill):
    key = "customer_type"
    slot = "customer_type"
    label = L("New or returning")
    description = L("Asks whether they've been here before (skipped when caller ID shows past visits).")
    default_enabled = False
    options = (FieldSpec("detect_from_history", L("Recognise returning callers by phone number"), "bool", default=True),)
    defaults = {"detect_from_history": True}
    lines = (line("ask", "Have you been with us before, or is this your first visit?", label="Ask new or returning", static=True),)
    synonyms = {
        "new": ("new", "first", "never"),
        "existing": ("existing", "returning", "been before", "before", "old patient", "regular"),
    }
    volunteerable = frozenset({"customer_type"})
    goal = "Find out whether this is their first visit or they've been before."

    def __init__(self, key: str | None = None, *, slot: str = "customer_type", noun: str = "customer", **overrides: Any) -> None:
        super().__init__(key, **overrides)
        self.slot = slot
        self.slots = (SlotSpec(slot, f"new = first visit, existing = a returning {noun}. Only if they say so.", {"type": "string", "enum": ["new", "existing"]}),)

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        if slots.get(self.slot) or not b.opt("detect_from_history", True):
            return
        if int(getattr(ctx, "caller_history", 0) or 0) > 0 or ctx.caller_records:
            slots[self.slot] = "existing"

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("ask", language)

    def commit_details(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        return {self.slot: slots[self.slot]} if slots.get(self.slot) else {}

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask", language)]


__all__ = ["CustomerTypeSkill"]
