"""The salon's pipeline flow: what is genuinely salon — facts, read-back, commit (per-staff capacity), outcomes."""

from __future__ import annotations

import re

from typing import Any

from app.flows.base import OUTCOME_BOOKED, OUTCOME_CANCELLED, OUTCOME_RESCHEDULED, CommitAction, CommitResult, Instruction
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.steps import CONFIRMED
from app.flows.timefmt import calendar_facts
from app.pipeline.blueprint import Branch
from app.pipeline.flow import PipelineFlow
from app.verticals.common import money, notice, slot_start, when_phrase
from app.verticals.reception.contact import caller_phone
from app.verticals.salon.catalog import (
    KIND_BOOKING,
    KIND_SERVICE,
    KIND_STAFF,
    assigned_staff,
    chosen_service,
    duration,
    price,
    record_service,
    record_staff,
    service_facts,
    staff_facts,
    with_article,
)
from app.voice.languages import normalize_language

RULES = """You are the receptionist of a hair salon / beauty salon / spa. You book appointments for services and move or cancel existing ones; the system finds the time.
- Services are referred to by ref (S1, S2, …): save the one the caller wants as `service`. Staff (stylists, therapists) by ref (T1, T2, …): save the one they ask for as `staff`, or staff = "any" when anyone is fine. If a service could be one of several, let the system ask.
- The caller's name goes in `customer_name` (not in `note`).
- Prices and durations come only from the list. Never promise a result, a discount, or a price for something not on the list — say the stylist will advise at the appointment.
- Intent: book = new appointment, reschedule = move an existing one, cancel = cancel an existing one. Questions about services, prices, staff or opening hours are answered from the facts below, then ask whether they would like to book.
- Dates: save `date` as YYYY-MM-DD from the calendar below (a weekday means the next such day). A preferred time goes in `time_pref` as HH:MM (24 h) or morning/afternoon/evening.
- Existing bookings of this caller are listed with refs (A1, A2, …); save the chosen one as `booking`.
- Availability: you never know which times are free — the system does (it allows for how long the service takes and who is in). Save date / time_pref and the system proposes the nearest free time.
- The system reads the summary back and writes the booking. Never say a booking is made, moved or cancelled before a tool result says so."""

COMPACT_RULES = """Salon / spa receptionist: book, move or cancel appointments; the system finds the time.
- `service` = the S-ref; `staff` = the T-ref they ask for, or "any"; the caller's name → `customer_name`. Prices and durations only from the facts.
- intent: book | reschedule | cancel. Answer questions from the facts, then offer a booking.
- You never know free times — save date/time_pref and the system proposes one."""



#: Service notes that ask something of the client (read back so nobody turns up unprepared).
_REQUIREMENT_RE = re.compile(r"\b(patch test|before|required|must|bring|arrive|consultation|no .* within)\b", re.IGNORECASE)


def requirement_note(service: Any) -> str:
    note = " ".join(str((service.get("notes") if service is not None else "") or "").split()).rstrip(".")
    return f"Please note: {note[0].lower()}{note[1:]}." if note and _REQUIREMENT_RE.search(note) else ""

class SalonFlow(PipelineFlow):
    RULES = RULES
    COMPACT_RULES = COMPACT_RULES

    # ---- helpers ---------------------------------------------------------------------------------
    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def lookup(self):  # noqa: ANN201
        return self.cp.bound.get("lookup")

    def intent(self, slots: dict[str, Any]) -> str:
        return str(slots.get("intent") or "book")

    def target(self, slots: dict[str, Any], ctx: CallContext) -> Any | None:
        lookup = self.lookup()
        return lookup.skill.target(slots, ctx) if lookup else None

    def confirms_cancellation(self, slots: dict[str, Any], ctx: CallContext) -> bool:
        return ctx.direction == DIRECTION_INBOUND and slots.get("intent") == "cancel"

    def _when(self, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        start = slot_start(slots)
        return when_phrase(start, ctx, language) if start else ""

    def _words(self, service: CatalogEntry | None, person: CatalogEntry | None, language: str, *, article: bool = True) -> dict[str, str]:
        """``{service}`` reads "a haircut" in a new booking, "haircut" after "your"."""
        name = service.name if service else ""
        return {"service": with_article(name, language) if article else name, "staff": person.name if person else ""}

    # ---- slots -----------------------------------------------------------------------------------
    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        lookup = self.lookup()
        if slots.get("intent") in ("cancel", "reschedule") and lookup is not None:
            lookup.skill.derive(lookup, slots, ctx)
            record = self.target(slots, ctx)
            service, person = record_service(record, ctx), record_staff(record, ctx)
            if service is not None:
                slots["service"] = service.ref  # a moved booking keeps its service and person
            if person is not None:
                slots["staff"] = person.ref
        super().derive(slots, ctx)

    # ---- read-back -------------------------------------------------------------------------------
    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        """New bookings also repeat a service's own requirement ("patch test 48 hours before")."""
        lang = normalize_language(language)
        confirm = self.lines
        intent = self.intent(slots)
        if intent == "cancel":
            record = self.target(slots, ctx)
            start = getattr(record, "scheduled_at", None)
            when = when_phrase(start.astimezone(ctx.now.tzinfo), ctx, lang, on=True) if start else ""
            words = self._words(record_service(record, ctx), record_staff(record, ctx), lang, article=False)
            return confirm.text("readback_cancel", lang, when=when, **words), ""
        service, person = chosen_service(slots, ctx), assigned_staff(slots, ctx)
        when = self._when(slots, ctx, lang)
        if intent == "reschedule":
            words = self._words(service, person, lang, article=False)
            return confirm.text("readback_reschedule", lang, when=when, **words), confirm.text("confirm_reschedule", lang)
        words = self._words(service, person, lang)
        cost = price(service)
        price_part = confirm.text("price_part", lang, price=money(cost, ctx, lang)) if cost else ""
        key = "readback_book" if person is not None else "readback_book_any"
        summary = confirm.text(key, lang, when=when, price_part=price_part, minutes=str(duration(service)), **words)
        return " ".join(part for part in (summary, requirement_note(service)) if part), confirm.text("confirm_book", lang)

    # ---- commit --------------------------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        intent = self.intent(slots)
        record = self.target(slots, ctx) if intent in ("cancel", "reschedule") else None
        if intent == "cancel":
            return CommitAction(outcome=OUTCOME_CANCELLED, status="cancelled", record_id=str(record.id)) if record is not None else None
        service, person, start = chosen_service(slots, ctx), assigned_staff(slots, ctx), slot_start(slots)
        if service is None or start is None:
            return None
        resource = person.id if person else None
        details = {"service": service.name, "service_id": service.id, "staff": person.name if person else "", "duration_minutes": duration(service)}
        if intent == "reschedule":
            if record is None:
                return None
            return CommitAction(
                outcome=OUTCOME_RESCHEDULED,
                status="confirmed",
                record_id=str(record.id),
                fields={"scheduled_at": start, "catalog_item_id": resource, "details": details},
                capacity=(resource, start, 1),
            )
        return CommitAction(
            outcome=OUTCOME_BOOKED,
            status="confirmed",
            fields={
                "kind": KIND_BOOKING,
                "customer_name": slots.get("customer_name", ""),
                "customer_phone": caller_phone(slots, ctx),
                "catalog_item_id": resource,
                "scheduled_at": start,
                "items_summary": f"{service.name} — {person.name}" if person else service.name,
                "total_amount": price(service),
                "details": details,
            },
            # One client at a time per person (per salon without a staff list).
            capacity=(resource, start, 1),
        )

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start, person = slot_start(slots), assigned_staff(slots, ctx)
        if start is not None:
            ctx.mark_booked(person.id if person else None, start, 99)
        slots[CONFIRMED] = None
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- closings ------------------------------------------------------------------------------------
    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        confirm = self.lines
        when = self._when(slots, ctx, language)
        if outcome == OUTCOME_BOOKED:
            return confirm.text("closing_booked", language, when=when, **self._words(chosen_service(slots, ctx), assigned_staff(slots, ctx), language))
        if outcome == OUTCOME_RESCHEDULED:
            return confirm.text("closing_rescheduled", language, when=when)
        if outcome == OUTCOME_CANCELLED:
            return confirm.text("closing_cancelled", language)
        return ""

    # ---- prompt parts ----------------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return self.RULES

    def compact_rules(self, language: str) -> str:
        return self.COMPACT_RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        return [*service_facts(ctx), *staff_facts(ctx)]

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        lines.append(f"Caller's number: {ctx.caller_number}." if ctx.caller_number else "Caller's number is unknown — the system will ask for it.")
        lookup = self.lookup()
        mine = lookup.skill.records(ctx) if lookup else []
        if mine:
            lines.append("This caller's upcoming bookings:")
            for index, record in enumerate(mine, start=1):
                service, person = record_service(record, ctx), record_staff(record, ctx)
                stamp = record.scheduled_at.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M")
                lines.append(f"- A{index}: {stamp} {service.name if service else 'booking'}{f' with {person.name}' if person else ''}")
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [item.name for item in ctx.items(KIND_SERVICE)][:8]
        hints += [item.name for item in ctx.items(KIND_STAFF)][:8]
        return hints


__all__ = ["COMPACT_RULES", "RULES", "SalonFlow"]
