"""Emergencies: any time in the call, give the local emergency number and, on a phone
call, offer to put the caller straight through (``connect_emergency`` on a yes)."""

from __future__ import annotations

import re
from typing import Any

from app.flows.base import OUTCOME_EMERGENCY, Terminal
from app.flows.context import CallContext
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import line
from app.verticals.base import FieldSpec, L

REPORT = "report_emergency"
CONNECT = "connect_emergency"

#: Said in the offer when the account connects to its own on-call line instead of a short code.
ON_CALL_LINE = {"en": "our emergency line"}

#: The offer and the line said while connecting; vertical wording keeps these next to its own emergency line.
CONNECT_LINES = (
    line("offer", "Would you like me to connect you to {target} now?", label="Offer to connect", variables=("target", "emergency")),
    line("connecting", "Connecting you now. Tell them your exact address right away.", label="While connecting", static=True),
    line("goodbye", "Okay. Please stay safe, and call {emergency} if you need help. Goodbye.", label="If they say no", variables=("emergency",)),
)


def is_short_code(number: str) -> bool:
    """"911", "112", "999": dialled and spoken exactly as written."""
    digits = re.sub(r"\D", "", str(number or ""))
    return 0 < len(digits) <= 4


class EmergencySkill(Skill):
    key = "emergency"
    kind = "global"
    toggleable = False
    label = L("Emergencies")
    description = L("Recognises emergencies, gives the emergency number and offers to connect the caller.")
    options = (
        FieldSpec("red_flags", L("What counts as an emergency"), "list"),
        FieldSpec("connect", L("Offer to connect the caller"), "bool", default=True, help=L("Phone calls only. The agent asks first and connects on a yes.")),
        FieldSpec("connect_to", L("Connect to"), "phone", help=L("Blank = your emergency number. Or an on-call line.")),
    )
    lines = (
        line(
            "emergency",
            "This sounds like an emergency. Please call {emergency} right now.",
            label="Emergency line",
            variables=("emergency",),
            required=("emergency",),
        ),
        *CONNECT_LINES,
    )

    def __init__(self, key: str | None = None, *, red_flags: tuple[str, ...] = (), **overrides: Any) -> None:
        super().__init__(key, **overrides)
        self.defaults = {"red_flags": list(red_flags), "connect": True, "connect_to": ""}

    def terminals(self, b: BoundSkill) -> list[Terminal]:
        flags = ", ".join(str(f) for f in (b.opt("red_flags") or [])[:20]) or "a life-threatening situation"
        return [
            Terminal(
                name=REPORT,
                outcome=OUTCOME_EMERGENCY,
                description=f"The caller describes an emergency ({flags}). Call at once.",
                properties={"what": {"type": "string", "description": "What the caller described, a few words."}},
                note_template={"en": "Emergency: {what}"},
                requires_identity=False,
            ),
            Terminal(
                name=CONNECT,
                outcome=OUTCOME_EMERGENCY,
                description="Put the caller through to emergency help: only after you offered and they said yes, or they ask to be connected.",
                note_template={"en": "Emergency: put through"},
                requires_identity=False,
            ),
        ]

    # ---- connecting (phone calls) --------------------------------------------------
    def connect_target(self, b: BoundSkill, ctx: CallContext) -> str:
        """The number a yes connects to; '' = never offer (switched off, or nothing to dial)."""
        if not b.opt("connect", True):
            return ""
        return str(b.opt("connect_to") or "").strip() or str(ctx.emergency_number or "").strip()

    def target_words(self, b: BoundSkill, target: str, ctx: CallContext, language: str) -> str:
        if is_short_code(target):
            return ctx.say_number(target, language)
        return ON_CALL_LINE.get(language, ON_CALL_LINE["en"])

    def offer(self, b: BoundSkill, target: str, ctx: CallContext, language: str) -> str:
        return b.text(
            "offer",
            language,
            target=self.target_words(b, target, ctx, language),
            emergency=ctx.say_number(ctx.emergency_number, language),
        )

    def connecting(self, b: BoundSkill, language: str) -> str:
        return b.text("connecting", language)

    def goodbye(self, b: BoundSkill, ctx: CallContext, language: str) -> str:
        """The caller didn't want to be put through and is done: a short safety reminder."""
        return b.text("goodbye", language, emergency=ctx.say_number(ctx.emergency_number, language))

    # ---- spoken lines ----------------------------------------------------------------
    def closing(self, b: BoundSkill, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if outcome != OUTCOME_EMERGENCY:
            return ""
        return b.text("emergency", language, emergency=ctx.say_number(ctx.emergency_number, language))

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        lines = [self.closing(b, OUTCOME_EMERGENCY, {}, ctx, language)]
        target = self.connect_target(b, ctx)
        if target:
            lines += [self.offer(b, target, ctx, language), self.connecting(b, language), self.goodbye(b, ctx, language)]
        return lines


__all__ = ["CONNECT", "CONNECT_LINES", "REPORT", "EmergencySkill", "is_short_code"]
