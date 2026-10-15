"""The custom engine's pipeline flow: generic wording ("our team"), bookings over resources, leads."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_BOOKED, OUTCOME_LEAD, CommitAction, CommitResult, Instruction
from app.flows.context import CallContext
from app.flows.steps import CONFIRMED
from app.flows.timefmt import calendar_facts
from app.pipeline.blueprint import Branch
from app.pipeline.flow import PipelineFlow
from app.skills.base import lang_pick
from app.verticals.common import notice, slot_start, when_phrase
from app.verticals.custom.catalog import KIND_BOOKING, KIND_LEAD, KIND_RESOURCE, chosen, resource_facts
from app.verticals.reception import caller_phone

RULES = """You answer the phone for the business below: book what it offers, take the details it asks for, and take messages for the team.
- Intent: book = book something from the list; inquiry = they want the team to get back to them about something; message = anything else for the team.
- Answer questions only from the facts and business information; for anything else, offer to take the caller's details for the team.
- Bookings: save `resource` as the ref from the list, `date` as YYYY-MM-DD from the calendar and `time_pref` as HH:MM; the system finds the free time.
- The system reads the details back and saves them; never say something is booked or passed on before a tool result says so."""

COMPACT_RULES = """Business phone agent: bookings (resource ref, date, time_pref), inquiries and messages for the team.
- Answer only from the facts; otherwise take their details for the team. Never say booked before a tool result."""


class CustomFlow(PipelineFlow):
    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def intent(self, slots: dict[str, Any]) -> str:
        return str(slots.get("intent") or "")

    def phone_words(self, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if slots.get("phone") or not ctx.caller_number:
            return ctx.say_number(caller_phone(slots, ctx), language)
        return "এই নম্বরে" if language == "bn" else "this number"

    def details(self, slots: dict[str, Any], language: str) -> list[str]:
        """The caller's answers to the owner's questions, as "Label: value" (name first)."""
        bound = self.cp.bound.get("intake")
        parts = [str(slots.get("customer_name") or "")]
        if bound is not None:
            for spec in bound.skill.fields(bound):
                value = slots.get(spec.key)
                if spec.key != "customer_name" and value not in (None, ""):
                    shown = ("yes" if value else "no") if isinstance(value, bool) else value
                    parts.append(f"{lang_pick(spec.label, language)}: {shown}")
        if slots.get("note"):
            parts.append(str(slots["note"]))
        return [part for part in parts if part]

    # ---- read-back ---------------------------------------------------------------------------------
    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        c = self.lines
        intent = self.intent(slots)
        if intent == "book":
            start = slot_start(slots)
            item = chosen(slots, ctx)
            summary = c.text("readback_book", language, resource=item.name if item else "", name=slots.get("customer_name", ""), when=when_phrase(start, ctx, language) if start else "")
            return summary, c.text("confirm_book", language)
        phone = self.phone_words(slots, ctx, language)
        if intent == "message":
            message = str(slots.get("message") or "").strip().rstrip(".!?।")
            return c.text("readback_message", language, message=message, phone=phone), c.text("confirm_lead", language)
        return c.text("readback_inquiry", language, details=", ".join(self.details(slots, language)), phone=phone), c.text("confirm_lead", language)

    # ---- commit ------------------------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        intent = self.intent(slots)
        base = {"customer_name": str(slots.get("customer_name") or ""), "customer_phone": caller_phone(slots, ctx), "notes": str(slots.get("note") or "")}
        if intent == "book":
            start = slot_start(slots)
            item = chosen(slots, ctx)
            if start is None or item is None:
                return None
            capacity = int(item.get("capacity") or 1)
            return CommitAction(
                outcome=OUTCOME_BOOKED,
                status="confirmed",
                fields={**base, "kind": KIND_BOOKING, "catalog_item_id": item.id, "scheduled_at": start, "items_summary": item.name,
                        "total_amount": item.get("price") or 0, "details": {"type": "booking", "resource": item.name}},
                capacity=(item.id, start, max(1, capacity)),
            )
        if intent not in ("inquiry", "message"):
            return None
        summary = str(slots.get("message") or "") if intent == "message" else ", ".join(self.details(slots, "en")[1:])
        details = {"type": intent}
        if intent == "message":
            details["message"] = slots.get("message", "")
        return CommitAction(outcome=OUTCOME_LEAD, status="needs_review", fields={**base, "kind": KIND_LEAD, "items_summary": summary or "Inquiry", "details": details})

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start = slot_start(slots)
        item = chosen(slots, ctx)
        if start is not None:
            ctx.mark_booked(item.id if item else None, start, 999)
        slots[CONFIRMED] = None
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- closings ------------------------------------------------------------------------------------
    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if outcome == OUTCOME_BOOKED:
            start = slot_start(slots)
            return self.lines.text("closing_booked", language, when=when_phrase(start, ctx, language) if start else "")
        if outcome == OUTCOME_LEAD:
            return self.lines.text("closing_lead", language)
        return ""

    # ---- prompt parts ----------------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return RULES

    def compact_rules(self, language: str) -> str:
        return COMPACT_RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        return resource_facts(ctx)

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        assert ctx.now is not None
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.caller_number:
            lines.append(f"Caller's number: {ctx.caller_number} (used to reach them unless they give another).")
        else:
            lines.append("Caller's number is unknown — the system will ask for one.")
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        return [str(ctx.merchant_value("business_name", "")), *[item.name for item in ctx.items(KIND_RESOURCE)][:10]]


__all__ = ["COMPACT_RULES", "RULES", "CustomFlow"]
