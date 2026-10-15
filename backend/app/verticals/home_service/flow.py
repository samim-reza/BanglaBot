"""The home-service pipeline flow: what is genuinely home-service — facts, read-back, commit, outcomes."""

from __future__ import annotations

from typing import Any

from app.flows.base import (
    OUTCOME_BOOKED,
    OUTCOME_CANCELLED,
    OUTCOME_CONFIRMED,
    OUTCOME_LEAD,
    OUTCOME_RESCHEDULED,
    CommitAction,
    CommitResult,
    Instruction,
)
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import CONFIRMED
from app.flows.timefmt import calendar_facts
from app.pipeline.blueprint import Branch
from app.pipeline.flow import PipelineFlow
from app.verticals.common import notice, slot_start
from app.verticals.home_service.catalog import (
    KIND_BOOKING,
    area_facts,
    chosen_service,
    price_parts,
    record_service,
    record_when,
    service_areas,
    service_facts,
    teams,
    visit_when,
)
from app.verticals.reception.contact import caller_phone
from app.voice.languages import normalize_language

RULES = """You are the phone assistant of a home-services company (e.g. AC / heating, plumbing, electrical, cleaning, pest control, appliance repair). You book technician visits.
- Map the caller's problem to one service from the list and save its ref (S1, S2, …) as `service`; save their description (a few words) as `problem`. If two services could fit, let the system ask.
- Price: only the visit charge and the usual price range from the list. Never promise an exact job price or an exact arrival minute — the technician quotes after inspection and comes within the booked window.
- Never give do-it-yourself repair instructions for gas or electrical work.
- Emergency (gas smell or leak, sparks, burning smell from wiring, fire, electric shock, major flooding near electrics): call report_emergency immediately.
- Address: save the full address as `address` and the neighbourhood / locality as `area`.
- Dates: save `date` as YYYY-MM-DD from the calendar below; a preferred arrival window goes in `time_window` (morning / afternoon / evening). The system picks the window, reads the booking back and writes it. Never say a booking is confirmed before a tool result says so.
- intent stays book unless the caller asks to move (reschedule) or cancel an existing booking; their bookings are listed with refs (A1, A2, …) — save the chosen one as `booking`."""

COMPACT_RULES = """Home-services assistant: book technician visits (arrival windows), move or cancel bookings.
- `service` = the S-ref matching the problem (several fit → let the system ask); `problem` = a few words.
- Only the visit charge and usual range from the facts; never an exact job price or arrival minute. No DIY gas/electrical advice.
- Gas smell, sparks, fire, shock, flooding near electrics → report_emergency at once.
- Save address + area; date (YYYY-MM-DD) + time_window. intent is book unless they ask to move/cancel."""


class HomeServiceFlow(PipelineFlow):
    RULES = RULES
    COMPACT_RULES = COMPACT_RULES

    # ---- helpers ---------------------------------------------------------------------------------
    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def lookup(self):  # noqa: ANN201
        return self.cp.bound.get("lookup")

    def intent(self, slots: dict[str, Any], ctx: CallContext) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return str(slots.get("intent") or "book")
        if slots.get("time_ok") is True:
            return "confirm"
        if slots.get("wants_new_time") is False:
            return "cancel"
        return "reschedule"

    def target(self, slots: dict[str, Any], ctx: CallContext) -> Any | None:
        if ctx.direction != DIRECTION_INBOUND:
            return ctx.record
        lookup = self.lookup()
        return lookup.skill.target(slots, ctx) if lookup else None

    def confirms_cancellation(self, slots: dict[str, Any], ctx: CallContext) -> bool:
        return ctx.direction == DIRECTION_INBOUND and slots.get("intent") == "cancel"

    def _service_name(self, slots: dict[str, Any], ctx: CallContext) -> str:
        service = chosen_service(slots, ctx)
        return service.name if service else ""

    # ---- slots -----------------------------------------------------------------------------------
    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        slots = super().initial_slots(ctx)
        if ctx.direction != DIRECTION_INBOUND:
            slots["customer_name"] = ctx.record_value("customer_name", "")
            item = record_service(ctx.record, ctx)
            if item is not None:
                slots["service"] = item.ref
            if ctx.record_value("address", ""):
                slots["address"] = ctx.record_value("address", "")
        return slots

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        lookup = self.lookup()
        if ctx.direction == DIRECTION_INBOUND and slots.get("intent") in ("cancel", "reschedule") and lookup is not None:
            lookup.skill.derive(lookup, slots, ctx)
            item = record_service(self.target(slots, ctx), ctx)
            if item is not None:
                slots["service"] = item.ref  # a moved visit keeps its service
        super().derive(slots, ctx)

    # ---- read-back -------------------------------------------------------------------------------
    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        lang = normalize_language(language)
        confirm = self.lines
        intent = self.intent(slots, ctx)
        if intent == "cancel":
            target = self.target(slots, ctx)
            item = record_service(target, ctx)
            return confirm.text("readback_cancel", lang, service=item.name if item else "", when=record_when(target, ctx, lang)), ""
        if intent == "reschedule":
            return (
                confirm.text("readback_move", lang, service=self._service_name(slots, ctx), when=visit_when(slots, ctx, lang)),
                confirm.text("confirm_move", lang),
            )
        parts = price_parts(chosen_service(slots, ctx), ctx, lang)
        price = confirm.text("price_range" if "low" in parts else "price", lang, **parts) if parts else ""
        summary = confirm.text(
            "readback_book", lang, address=slots.get("address", ""), when=visit_when(slots, ctx, lang, on=True), service=self._service_name(slots, ctx), price=price
        )
        return summary, confirm.text("confirm_book", lang)

    # ---- commit --------------------------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        intent = self.intent(slots, ctx)
        target = self.target(slots, ctx)
        record_id = str(getattr(target, "id", "") or "") or None
        if intent == "confirm":
            return CommitAction(outcome=OUTCOME_CONFIRMED, status="confirmed", record_id=record_id)
        if intent == "cancel":
            if record_id is None:
                return None
            return CommitAction(outcome=OUTCOME_CANCELLED, status="cancelled", record_id=record_id)
        start = slot_start(slots)
        if start is None:
            return None
        if intent == "reschedule":
            if record_id is None:
                return None
            return CommitAction(
                outcome=OUTCOME_RESCHEDULED,
                status="confirmed",
                record_id=record_id,
                fields={"scheduled_at": start, "details": {"time_window": slots.get("window", "")}},
                capacity=(None, start, teams(ctx)),
            )
        service = chosen_service(slots, ctx)
        if service is None:
            return None
        return CommitAction(
            outcome=OUTCOME_BOOKED,
            status="confirmed",
            fields={
                "kind": KIND_BOOKING,
                "customer_name": slots.get("customer_name", ""),
                "customer_phone": caller_phone(slots, ctx),
                "address": slots.get("address", ""),
                "catalog_item_id": service.id,
                "scheduled_at": start,
                "items_summary": service.name,
                "total_amount": service.get("visit_charge") or 0,
                "details": {
                    "problem": slots.get("problem", ""),
                    "area": slots.get("area", ""),
                    "time_window": slots.get("window", ""),
                    "service": service.name,
                },
            },
            capacity=(None, start, teams(ctx)),
        )

    def fallback_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        """Inbound caller who stopped before booking (e.g. outside the service area): keep the request."""
        if ctx.direction != DIRECTION_INBOUND or self.intent(slots, ctx) != "book" or not (slots.get("service") or slots.get("problem")):
            return None
        phone = caller_phone(slots, ctx)
        if not phone:
            return None
        service = chosen_service(slots, ctx)
        return CommitAction(
            outcome=OUTCOME_LEAD,
            status="needs_review",
            fields={
                "kind": KIND_BOOKING,
                "customer_name": slots.get("customer_name", ""),
                "customer_phone": phone,
                "address": slots.get("address", ""),
                "catalog_item_id": service.id if service else None,
                "items_summary": service.name if service else str(slots.get("problem") or ""),
                "details": {"problem": slots.get("problem", ""), "area": slots.get("area", ""), "unfinished": True},
            },
        )

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start = slot_start(slots)
        if start is not None:
            ctx.mark_booked(None, start, 99)
        slots[CONFIRMED] = None
        slots.pop("time_window", None)
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- closings ------------------------------------------------------------------------------------
    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        confirm = self.lines
        if outcome in (OUTCOME_BOOKED, OUTCOME_RESCHEDULED):
            key = "closing_booked" if outcome == OUTCOME_BOOKED else "closing_rescheduled"
            return confirm.text(key, language, when=visit_when(slots, ctx, language))
        keys = {OUTCOME_CONFIRMED: "closing_confirmed", OUTCOME_CANCELLED: "closing_cancelled", OUTCOME_LEAD: "closing_lead"}
        return confirm.text(keys[outcome], language) if outcome in keys else ""

    def knows_person_line(self, ctx: CallContext, language: str) -> str:
        return self.lines.text("knows_person", language, name=self.person_name(ctx))

    # ---- prompt parts ----------------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return self.RULES

    def compact_rules(self, language: str) -> str:
        return self.COMPACT_RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        return [*service_facts(ctx), *area_facts(ctx), f"Emergency number: {ctx.emergency_number}."]

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.direction == DIRECTION_INBOUND:
            lines.append(f"Caller's number: {ctx.caller_number}." if ctx.caller_number else "Caller's number is unknown — the system will ask for it.")
            lookup = self.lookup()
            mine = lookup.skill.records(ctx) if lookup else []
            if mine:
                lines.append("This caller's upcoming bookings:")
                for index, record in enumerate(mine, start=1):
                    item = record_service(record, ctx)
                    stamp = record.scheduled_at.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M")
                    lines.append(f"- A{index}: {stamp} {item.name if item else 'visit'} at {getattr(record, 'address', '') or '?'}")
        else:
            item = record_service(ctx.record, ctx)
            start = getattr(ctx.record, "scheduled_at", None)
            stamp = start.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M") if start else "?"
            lines.append(
                f"This call confirms {self.person_name(ctx)}'s booking: {item.name if item else 'service'} on {stamp} "
                f"at {ctx.record_value('address', '?')}."
            )
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [item.name for item in ctx.items("service")][:8]
        hints += service_areas(ctx)[:10]
        return hints


__all__ = ["COMPACT_RULES", "RULES", "HomeServiceFlow"]
