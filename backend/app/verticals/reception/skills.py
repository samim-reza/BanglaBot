"""Reception-only skills: help the caller (answer or take the request), and the read-back / closing wording."""

from __future__ import annotations

import re

from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill, lang_pick
from app.skills.library.lines import L, line
from app.verticals.common import notice
from app.voice.languages import spoken_amount

STAGE_HELP = "help"

_GUIDANCE = {
    "en": "Answer the caller from the business facts only. Asked about their order? First tell them what the facts say about it "
    "(status, items, total) in reply. Only what you can't answer or what needs staff (a cancellation or change request, a complaint, "
    "a delivery date you don't have) — save it as message.",
}
_STATUS_WORDS = re.compile(r"\b(status|where is|where's|arrive|arriving|delivery|deliver|track|tracking|shipped|ship|when will)\b", re.IGNORECASE)
_CANCEL_WORDS = re.compile(r"\b(cancel|cancelled|canceled|cancellation|don't want it|do not want it)\b", re.IGNORECASE)
_STATUS_PHRASES = {
    "pending": "waiting to be confirmed before it ships",
    "confirmed": "confirmed and being prepared",
    "needs_review": "with our team for a quick review",
    "completed": "completed",
    "cancelled": "cancelled",
    "shipped": "on its way",
    "delivered": "delivered",
}
#: Orders of this caller shown to the model (most recent first).
MAX_ORDERS = 3


def caller_orders(ctx: CallContext) -> list[str]:
    """The caller's own orders on file (found by caller ID), as facts the agent may state."""
    out: list[str] = []
    for record in list(ctx.caller_records)[:MAX_ORDERS]:
        if str(getattr(record, "kind", "") or "") not in ("order", "OrderKind.order"):
            continue
        status = str(getattr(getattr(record, "status", ""), "value", getattr(record, "status", "")) or "")
        ref = str(getattr(record, "order_ref", "") or "") or "no number"
        total = getattr(record, "total_amount", None)
        amount = f"{total} {ctx.currency}".strip() if total not in (None, "") else ""
        items = str(getattr(record, "items_summary", "") or "")
        out.append(f"Caller's order {ref}: {items or 'items on file'}{', ' + amount if amount else ''}; status: {status.replace('_', ' ')}.")
    return out


class HelpSkill(Skill):
    """Answers from the facts (the model, in its own words); a request staff must handle becomes the message."""

    key = "help"
    label = L("Questions and requests")
    description = L("Answers from your business information; anything else is taken as a message.")
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
    goal = (
        "Help the caller from the business facts. Asked about their order? Tell them its status from the facts first (in reply). "
        "Save message only for what needs staff: a change or cancellation, a complaint, a delivery date you don't have."
    )

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return (STAGE_HELP,)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return None if slots.get("message") else STAGE_HELP

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction:
        return Instruction(STAGE_HELP, lang_pick(_GUIDANCE, language))

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return caller_orders(ctx)

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        """"Where's my order?" from a caller with an order on file: say its status before taking the message."""
        message = str(saved.get("message") or "")
        order = next((r for r in ctx.caller_records if str(getattr(r, "kind", "") or "").endswith("order")), None)
        if order is None:
            return
        if _CANCEL_WORDS.search(message):
            # A cancellation goes to the team, against the right order.
            notice(slots, "order_cancel_request", ref=str(getattr(order, "order_ref", "") or "on file"))
            return
        if not _STATUS_WORDS.search(message):
            return
        status = str(getattr(getattr(order, "status", ""), "value", getattr(order, "status", "")) or "")
        total = getattr(order, "total_amount", None)
        notice(
            slots,
            "order_status",
            ref=str(getattr(order, "order_ref", "") or "on file"),
            items=str(getattr(order, "items_summary", "") or "your items"),
            total=spoken_amount(total, ctx.currency, "en") if total not in (None, "") else "",
            status=_STATUS_PHRASES.get(status, status.replace("_", " ") or "being processed"),
        )


class ReceptionConfirmSkill(Skill):
    """Holds the read-back and closing wording (editable); the flow assembles them."""

    key = "confirm"
    kind = "line"
    toggleable = False
    label = L("Read-back and closing")
    description = L("What is read back before the message is passed on, and what is said after.")
    lines = (
        line(
            "readback",
            "So your name is {name}, and your message is: {message}. A team member will call you on {phone} — is that right?",
            label="Read-back (number given)",
            variables=("name", "message", "phone"),
        ),
        line(
            "readback_own_number",
            "So your name is {name}, and your message is: {message}. A team member will call you back on this number — is that right?",
            label="Read-back (caller's own number)",
            variables=("name", "message"),
        ),
        line(
            "closing_lead",
            "Thank you. One of our team will get in touch with you shortly.",
            label="After taking the message",
            static=True,
        ),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("closing_lead", language)]


__all__ = ["STAGE_HELP", "HelpSkill", "ReceptionConfirmSkill"]
