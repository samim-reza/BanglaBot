"""The clinic's pipeline flow: what is genuinely clinic-specific — facts, read-back, commit, outcomes."""

from __future__ import annotations

from typing import Any

from app.flows.base import (
    OUTCOME_BOOKED,
    OUTCOME_CANCELLED,
    OUTCOME_CONFIRMED,
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
from app.verticals.clinic.catalog import (
    KIND_APPOINTMENT,
    KIND_DOCTOR,
    chosen_doctor,
    doctor_facts,
    doctor_title,
    record_serial,
    record_start,
)
from app.verticals.clinic.skills import appointment_line, serial_part
from app.verticals.common import money, notice, slot_start, when_phrase
from app.verticals.reception import caller_phone
from app.voice.languages import normalize_language

RULES = """You are the receptionist of a doctor's practice / clinic. You book doctor appointments and move or cancel existing ones. The system computes the appointment time (and queue number, where used).
- Never diagnose, never suggest medicines, tests or doses, never say whether a symptom is serious. For medical questions say the doctor will advise at the visit; if the facts list a health advice line, you may suggest it.
- Emergency (chest pain, breathing difficulty, stroke signs, heavy bleeding, unconsciousness, seizure, severe injury, pregnancy bleeding or severe pain, poisoning): call report_emergency immediately, nothing else.
- Never reveal another patient's details.
- Doctors: when saving `doctor`, use the ref from the doctor list (D1, D2, …). If the caller describes a problem instead of naming a doctor, you may name the matching department from the list (never diagnose); if several doctors fit, let the system ask.
- Intent: book = new appointment, reschedule = move an existing one, cancel = cancel an existing one. Questions about doctors, days, timings, fees or the address are answered from the facts below, then ask whether they would like an appointment.
- Dates: save `date` as YYYY-MM-DD from the calendar below ("tomorrow"/"কাল" = the next day, "the day after"/"পরশু" = two days ahead; a weekday means the next such day). A preferred time goes in `time_pref` as HH:MM (24 h) or morning/afternoon/evening.
- Existing appointments of this caller are listed with refs (A1, A2, …); save the chosen one as `appointment`.
- Availability: you never know which times are free — the system does. When the caller wants another day or time, save it (date / time_pref) and the system proposes the nearest free time; never say a time is or isn't available yourself.
- The system reads the summary back and writes the booking. Never say an appointment is booked, moved or cancelled before a tool result says so."""


COMPACT_RULES = """Clinic receptionist: book, move or cancel doctor appointments; the system picks times (and queue numbers).
- Never diagnose or suggest medicines/tests; the doctor advises at the visit. Emergency signs → report_emergency at once.
- `doctor` = the D-ref from the facts (a described problem may map to a department; several fits → let the system ask).
- intent: book | reschedule | cancel. Answer questions from the facts, then offer an appointment.
- You never know free times — save date/time_pref and the system proposes one. Never reveal other patients' details."""


class ClinicFlow(PipelineFlow):
    #: Rules for the full (cached) and compact prompt profiles — subclasses (dental, vet) replace them.
    RULES = RULES
    COMPACT_RULES = COMPACT_RULES

    # ---- helpers ---------------------------------------------------------------------------------
    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def lookup(self):  # noqa: ANN201
        return self.cp.bound.get("lookup")

    def person_name(self, ctx: CallContext) -> str:
        return str(ctx.record_value("customer_name", ""))

    def target(self, slots: dict[str, Any], ctx: CallContext) -> Any | None:
        if ctx.direction != DIRECTION_INBOUND:
            return ctx.record
        lookup = self.lookup()
        return lookup.skill.target(slots, ctx) if lookup else None

    def intent(self, slots: dict[str, Any], ctx: CallContext) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return str(slots.get("intent") or "book")
        if slots.get("attend") is True:
            return "confirm"
        if slots.get("wants_new_time") is False:
            return "cancel"
        return "reschedule"

    def confirms_cancellation(self, slots: dict[str, Any], ctx: CallContext) -> bool:
        return ctx.direction == DIRECTION_INBOUND and slots.get("intent") == "cancel"

    def _when(self, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        start = slot_start(slots)
        return when_phrase(start, ctx, language) if start else ""

    # ---- slots -----------------------------------------------------------------------------------
    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        slots = super().initial_slots(ctx)
        if ctx.direction != DIRECTION_INBOUND:
            record = ctx.record
            item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
            if item is not None:
                slots["doctor"] = item.ref
            if record is not None:
                slots["patient_name"] = getattr(record, "customer_name", "")
        return slots

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        lookup = self.lookup()
        if ctx.direction == DIRECTION_INBOUND and slots.get("intent") in ("cancel", "reschedule") and lookup is not None:
            lookup.skill.derive(lookup, slots, ctx)
            if slots.get("appointment") and slots.get("intent") == "reschedule":
                # Moving an appointment keeps its doctor.
                item = ctx.item_by_id(getattr(self.target(slots, ctx), "catalog_item_id", None))
                if item is not None:
                    slots["doctor"] = item.ref
        super().derive(slots, ctx)

    # ---- read-back -------------------------------------------------------------------------------
    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        lang = normalize_language(language)
        confirm = self.lines
        intent = self.intent(slots, ctx)
        doctor = chosen_doctor(slots, ctx)
        if intent == "cancel":
            when, title, _ = appointment_line(self.target(slots, ctx), ctx, lang)
            patient = getattr(self.target(slots, ctx), "customer_name", "") or ""
            return confirm.text("readback_cancel", lang, when=when, doctor=title, patient=patient), ""
        when = self._when(slots, ctx, lang)
        part = serial_part(slots.get("serial"), ctx, lang, confirm)
        if intent == "reschedule":
            return (
                confirm.text("readback_reschedule", lang, doctor=doctor_title(doctor, lang), when=when, serial_part=part),
                confirm.text("confirm_reschedule", lang),
            )
        fee = doctor.get("fee") if doctor else None
        fee_part = " " + confirm.text("fee_part", lang, fee=money(fee, ctx, lang)) if fee else ""
        summary = confirm.text(
            "readback_book", lang, patient=slots.get("patient_name", ""), when=when, doctor=doctor_title(doctor, lang), serial_part=part, fee_part=fee_part
        )
        return summary, confirm.text("confirm_book", lang)

    # ---- commit --------------------------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        intent = self.intent(slots, ctx)
        doctor = chosen_doctor(slots, ctx)
        target = self.target(slots, ctx)
        if intent == "confirm":
            return CommitAction(outcome=OUTCOME_CONFIRMED, status="confirmed", record_id=str(getattr(target, "id", "") or "") or None)
        if intent == "cancel":
            if target is None:
                return None
            return CommitAction(outcome=OUTCOME_CANCELLED, status="cancelled", record_id=str(getattr(target, "id", "")))
        start = slot_start(slots)
        if doctor is None or start is None:
            return None
        details = {"serial": int(slots.get("serial") or 1), "doctor": doctor.name, "specialty": doctor.get("specialty", "")}
        if slots.get("reason"):
            details["reason"] = slots["reason"]
        if intent == "reschedule":
            if target is None:
                return None
            return CommitAction(
                outcome=OUTCOME_RESCHEDULED,
                status="confirmed",
                record_id=str(getattr(target, "id", "")),
                fields={"scheduled_at": start, "catalog_item_id": doctor.id, "details": details},
                capacity=(doctor.id, start, 1),
            )
        fee = doctor.get("fee")
        return CommitAction(
            outcome=OUTCOME_BOOKED,
            status="confirmed",
            fields={
                "kind": KIND_APPOINTMENT,
                "customer_name": slots.get("patient_name", ""),
                "customer_phone": caller_phone(slots, ctx),
                "catalog_item_id": doctor.id,
                "scheduled_at": start,
                "items_summary": f"{doctor.name} — {doctor.get('specialty', '')}".strip(" —"),
                "total_amount": fee or 0,
                "details": details,
            },
            capacity=(doctor.id, start, 1),
        )

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start = slot_start(slots)
        doctor = chosen_doctor(slots, ctx)
        if start is not None:
            ctx.mark_booked(doctor.id if doctor else None, start, 99)
        slots[CONFIRMED] = None
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- closings ------------------------------------------------------------------------------------
    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        confirm = self.lines
        when = self._when(slots, ctx, lang)
        part = serial_part(slots.get("serial"), ctx, lang, confirm)
        if outcome == OUTCOME_BOOKED:
            return confirm.text("closing_booked", lang, when=when, serial_part=part)
        if outcome == OUTCOME_RESCHEDULED:
            return confirm.text("closing_rescheduled", lang, when=when, serial_part=part)
        if outcome == OUTCOME_CONFIRMED:
            return confirm.text("closing_confirmed", lang)
        if outcome == OUTCOME_CANCELLED:
            return confirm.text("closing_cancelled", lang)
        return ""

    def knows_person_line(self, ctx: CallContext, language: str) -> str:
        return self.lines.text("knows_person", language, name=self.person_name(ctx))

    # ---- prompt parts ----------------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return self.RULES

    def compact_rules(self, language: str) -> str:
        return self.COMPACT_RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = doctor_facts(ctx)
        lines.append(f"Emergency number: {ctx.emergency_number}.")
        health_line = str(ctx.config.get("health_line") or ctx.region.health_line or "").strip()
        if health_line:
            lines.append(f"Health advice line (non-emergency): {health_line}.")
        return lines

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.direction == DIRECTION_INBOUND:
            if ctx.caller_number:
                lines.append(f"Caller's number: {ctx.caller_number} (used as the patient's contact unless they give another).")
            else:
                lines.append("Caller's number is unknown — the system will ask for a mobile number.")
            lookup = self.lookup()
            mine = lookup.skill.records(ctx) if lookup else []
            if mine:
                lines.append("This caller's upcoming appointments:")
                for index, record in enumerate(mine, start=1):
                    start = record_start(record)
                    item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
                    stamp = start.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M") if start else "?"
                    lines.append(
                        f"- A{index}: {stamp} with {item.name if item else '?'} for {getattr(record, 'customer_name', '')}"
                        f", serial {record_serial(record) or '?'}"
                    )
        else:
            record = ctx.record
            item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
            start = record_start(record)
            stamp = start.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M") if start else "?"
            lines.append(
                f"This call is a reminder about {self.person_name(ctx)}'s appointment: {stamp} with "
                f"{item.name if item else '?'}, serial {record_serial(record) or '?'}."
            )
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [item.name for item in ctx.items(KIND_DOCTOR)][:8]
        hints += ["সিরিয়াল", "অ্যাপয়েন্টমেন্ট", "ডাক্তার"]
        if ctx.record is not None:
            hints.append(self.person_name(ctx))
        return hints


__all__ = ["RULES", "ClinicFlow"]
