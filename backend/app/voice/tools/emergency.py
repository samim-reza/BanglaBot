"""Emergencies on a phone call: offer to put the caller through, connect on a clear yes,
and otherwise carry on with whatever the caller wants.

``report_emergency`` speaks the emergency line plus the offer ("… Would you like me to
connect you to nine one one now?") instead of hanging up. The caller's next turn decides:
a clear yes connects at once (the fast path, no model); anything else is the caller's to
steer — a question, a booking, "I'll call them myself". A call that ends after the offer
without being put through still closes with the emergency line and is kept as an emergency.

Chats, browser calls and accounts that switched the offer off keep the plain ending: the
emergency line, then goodbye (or the business's support line)."""

from __future__ import annotations

from typing import Any

from app.flows import hearing
from app.flows.base import OUTCOME_EMERGENCY
from app.skills.library.emergency import CONNECT, is_short_code
from app.voice import emergency_dial
from app.voice.languages import phrase
from app.voice.tools.store import ToolResult
from app.voice.tools.text import _join

#: Slots (``_``-prefixed: call state, never asked or saved to the record).
OFFERED = "_emergency_offered"
ANSWERED = "_emergency_answered"
CONNECTED = "_emergency_connected"
WHAT = "_emergency_what"

#: "Put me through", "call them", "hurry": a yes to the offer without a yes word.
CONNECT_PHRASES = (
    "connect me", "connect us", "connect him", "connect her", "put me through", "put us through", "call them",
    "call 911", "call nine one one", "call an ambulance", "get an ambulance", "hurry", "go ahead", "please do",
    "do it", "yes please",
)
#: "Don't", "I'll call them myself": never a yes, whatever else is said ("he's not breathing" still can be).
DECLINE_WORDS = ("don't", "dont", "do not", "no need", "myself", "not necessary")

AFTER_OFFER = (
    "Wait for the answer. A yes → connect_emergency. Anything else (a question, a booking, they'll call "
    "themselves) → help with exactly that and don't repeat the offer."
)
ALREADY_OFFERED = "You already offered to connect them. Call connect_emergency only if they ask for it now; otherwise help with what they said."


def wants_connection(text: str) -> bool:
    """A clear yes to "Would you like me to connect you?" — never a question, never a no."""
    norm = " ".join(hearing.tokens(text))
    if not norm or hearing.looks_like_question(text) or "no" in hearing.classify(text):
        return False
    if any(f" {word} " in f" {norm} " for word in DECLINE_WORDS):
        return False
    return hearing.supports(text, "confirm") or any(phrase_ in norm for phrase_ in CONNECT_PHRASES)


class EmergencyMixin:
    """Mixed into :class:`~app.voice.tools.core.CallTools`."""

    def _emergency_skill(self) -> Any | None:
        cp = getattr(self.flow, "cp", None)
        bound = cp.bound.get("emergency") if cp is not None else None
        return bound if bound is not None and bound.enabled else None

    def emergency_target(self) -> str:
        """Where a yes connects to; '' = no offer (a chat or browser call, or the account switched it off)."""
        if not getattr(self, "phone_call", False):
            return ""
        bound = self._emergency_skill()
        if bound is not None:
            return bound.skill.connect_target(bound, self.runtime.ctx)
        return str(self.runtime.ctx.emergency_number or "").strip()

    def emergency_offer_pending(self) -> bool:
        """The offer was just spoken and the caller hasn't answered it yet."""
        slots = self.runtime.slots
        return bool(slots.get(OFFERED)) and not slots.get(ANSWERED) and not slots.get(CONNECTED)

    def _offer_line(self, target: str) -> str:
        ctx, language = self.runtime.ctx, self.language
        bound = self._emergency_skill()
        if bound is not None:
            return bound.skill.offer(bound, target, ctx, language)
        words = ctx.say_number(target, language) if is_short_code(target) else ctx.say_number(ctx.emergency_number, language)
        return phrase("emergency_offer", language, target=words)

    def _connecting_line(self) -> str:
        bound = self._emergency_skill()
        if bound is not None:
            return bound.skill.connecting(bound, self.language)
        return phrase("emergency_connecting", self.language)

    def _emergency_note(self, ending: str) -> str:
        what = str(self.runtime.slots.get(WHAT) or "").strip()
        return f"Emergency: {what} — {ending}" if what else f"Emergency — {ending}"

    async def _emergency(self, name: str, args: dict[str, Any], caller_text: str) -> ToolResult | None:
        """``report_emergency`` / ``connect_emergency`` on a call that can be put through; None = the plain ending."""
        target = self.emergency_target()
        if not target:
            return None
        slots = self.runtime.slots
        what = str(args.get("what") or "").strip()
        if what:
            slots[WHAT] = what[:160]
        if name == CONNECT or (slots.get(OFFERED) and wants_connection(caller_text)):
            return await self.connect_emergency()
        if slots.get(OFFERED):
            return ToolResult(payload={"ok": False, "reason": "already_offered", "instruction": ALREADY_OFFERED})
        slots[OFFERED] = True
        slots.pop(ANSWERED, None)
        ctx = self.runtime.ctx
        line = _join(self.flow.closing_line(OUTCOME_EMERGENCY, slots, ctx, self.language), self._offer_line(target))
        self._spoken_stage = ""
        return ToolResult(payload={"ok": True, "offered": True, "instruction": f"(said) {line} {AFTER_OFFER}"}, say=line, stop=True)

    async def connect_emergency(self) -> ToolResult:
        """Put the caller through now: the connecting line plays, then the bridge dials."""
        target = self.emergency_target()
        slots = self.runtime.slots
        slots[OFFERED] = slots[ANSWERED] = slots[CONNECTED] = True
        self.runtime.mark_decided(OUTCOME_EMERGENCY)
        await self._set_outcome(OUTCOME_EMERGENCY, self._emergency_note(f"put through to {target}."))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_EMERGENCY, "instruction": "Say nothing."},
            say=self._connecting_line(),
            transfer_to=emergency_dial.mark(target),
            stop=True,
            outcome=OUTCOME_EMERGENCY,
        )

    def _offer_left_open(self) -> bool:
        """The call is ending after the offer without the caller being put through (or anything else saved)."""
        slots = self.runtime.slots
        return bool(slots.get(OFFERED)) and not slots.get(CONNECTED) and not self.outcome and not self.completed

    def _goodbye_line(self, *, repeat_advice: bool) -> str:
        """After an offer the caller didn't take. Silence repeats the full advice (it may not have been heard)."""
        ctx, language = self.runtime.ctx, self.language
        if repeat_advice:
            return self.flow.closing_line(OUTCOME_EMERGENCY, self.runtime.slots, ctx, language)
        bound = self._emergency_skill()
        if bound is not None:
            return bound.skill.goodbye(bound, ctx, language)
        return phrase("emergency_goodbye", language, emergency=ctx.say_number(ctx.emergency_number, language))

    async def emergency_goodbye(self, ending: str, *, repeat_advice: bool = False) -> ToolResult:
        """Goodbye after an offer the caller didn't take: where to get help, kept as an emergency."""
        await self._set_outcome(OUTCOME_EMERGENCY, self._emergency_note(ending))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_EMERGENCY, "instruction": "Say nothing."},
            say=self._goodbye_line(repeat_advice=repeat_advice),
            hang_up=True,
            stop=True,
            outcome=OUTCOME_EMERGENCY,
        )


__all__ = ["ANSWERED", "CONNECTED", "EmergencyMixin", "OFFERED", "WHAT", "wants_connection"]
