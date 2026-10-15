"""Emergencies: any time in the call, tell the caller the local emergency number — nothing else."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_EMERGENCY, Terminal
from app.flows.context import CallContext
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.base import FieldSpec, L


class EmergencySkill(Skill):
    key = "emergency"
    kind = "global"
    toggleable = False
    label = L2("Emergencies", "জরুরি অবস্থা")
    description = L2("Recognises emergencies and gives the emergency number.", "জরুরি অবস্থা চিনে জরুরি নম্বর জানায়।")
    options = (FieldSpec("red_flags", L("What counts as an emergency", "কোনগুলো জরুরি"), "list"),)
    lines = (
        line(
            "emergency",
            "This sounds like an emergency. Please call {emergency} right now.",
            "এটা জরুরি অবস্থা মনে হচ্ছে। দয়া করে এখনই {emergency} নম্বরে ফোন করুন।",
            label="Emergency line",
            variables=("emergency",),
            required=("emergency",),
        ),
    )

    def __init__(self, key: str | None = None, *, red_flags: tuple[str, ...] = (), **overrides: Any) -> None:
        super().__init__(key, **overrides)
        self.defaults = {"red_flags": list(red_flags)}

    def terminals(self, b: BoundSkill) -> list[Terminal]:
        flags = ", ".join(str(f) for f in (b.opt("red_flags") or [])[:20]) or "a life-threatening situation"
        return [
            Terminal(
                name="report_emergency",
                outcome=OUTCOME_EMERGENCY,
                description=f"The caller describes an emergency ({flags}). Call at once.",
                properties={"what": {"type": "string", "description": "What the caller described, a few words."}},
                note_template={"bn": "জরুরি অবস্থা: {what}", "en": "Emergency: {what}"},
                requires_identity=False,
            )
        ]

    def closing(self, b: BoundSkill, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if outcome != OUTCOME_EMERGENCY:
            return ""
        return b.text("emergency", language, emergency=ctx.say_number(ctx.emergency_number, language))

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("emergency", language, emergency=ctx.say_number(ctx.emergency_number, language))]


__all__ = ["EmergencySkill"]
