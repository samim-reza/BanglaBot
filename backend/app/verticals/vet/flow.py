"""The vet clinic's flow: the clinic engine, with the pet in the read-back and on the record."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_BOOKED, CommitAction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.pipeline.blueprint import Branch
from app.verticals.clinic.catalog import chosen_doctor, doctor_facts, doctor_title
from app.verticals.clinic.flow import ClinicFlow
from app.verticals.clinic.skills import appointment_line, serial_part
from app.verticals.common import money
from app.verticals.vet.skills import emergency_vet, pet_name
from app.voice.languages import normalize_language

RULES = """You are the receptionist of a veterinary clinic. You book appointments for pets (check-ups, vaccinations, illness, injuries, dental, grooming where offered) and move or cancel existing ones. The system computes the appointment time (and queue number, where used).
- Never diagnose, never suggest medicines, doses or home treatments, never say whether a symptom is serious. Say the vet will advise at the visit.
- Animal emergency (poisoning — chocolate, xylitol, antifreeze, rat poison, human medicines; trouble breathing; hit by a car or a bad fall; a seizure; heavy bleeding; a bloated, hard belly or retching without vomiting; collapse): call report_emergency immediately, nothing else.
- Never reveal another client's details.
- Vets: when saving `doctor`, use the ref from the vet list (D1, D2, …). Match the need to the specialty in the list (exotics / birds, surgery, dental …); if several vets fit, let the system ask.
- The person on the phone is the owner: save their name as `owner_name`, the pet's name as `pet_name`, and `species` (dog, cat, bird, rabbit, other). A few words about the visit go in `reason` when the caller says them.
- Intent: book = new appointment, reschedule = move an existing one, cancel = cancel an existing one. Questions about vets, days, timings, fees or the address are answered from the facts below, then ask whether they would like an appointment.
- Dates: save `date` as YYYY-MM-DD from the calendar below (a weekday means the next such day). A preferred time goes in `time_pref` as HH:MM (24 h) or morning/afternoon/evening.
- Existing appointments of this caller are listed with refs (A1, A2, …); save the chosen one as `appointment`.
- Availability: you never know which times are free — the system does. Save date / time_pref and the system proposes the nearest free time.
- The system reads the summary back and writes the booking. Never say an appointment is booked, moved or cancelled before a tool result says so."""

COMPACT_RULES = """Vet clinic receptionist: book, move or cancel pet appointments; the system picks times.
- Never diagnose or suggest medicines; the vet advises at the visit. Poisoning, trouble breathing, hit by a car, seizure, heavy bleeding, bloated belly, collapse → report_emergency at once.
- `doctor` = the D-ref of the vet. Save owner_name, pet_name, species (dog/cat/bird/rabbit/other), reason (a few words).
- intent: book | reschedule | cancel. You never know free times — save date/time_pref."""

PET_KEYS = ("pet_name", "species", "breed", "pet_age")


class VetFlow(ClinicFlow):
    RULES = RULES
    COMPACT_RULES = COMPACT_RULES

    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        slots = super().initial_slots(ctx)
        if ctx.direction != DIRECTION_INBOUND and ctx.record is not None:
            slots["owner_name"] = getattr(ctx.record, "customer_name", "")
            if pet_name(ctx.record):
                slots["pet_name"] = pet_name(ctx.record)
        return slots

    # ---- read-back -------------------------------------------------------------------------------
    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        lang = normalize_language(language)
        intent = self.intent(slots, ctx)
        if intent == "reschedule":
            return super().readback_core(slots, ctx, lang)
        confirm = self.lines
        if intent == "cancel":
            target = self.target(slots, ctx)
            when, title, _ = appointment_line(target, ctx, lang)
            owner = str(getattr(target, "customer_name", "") or "")
            return confirm.text("readback_cancel", lang, when=when, doctor=title, pet=pet_name(target) or owner, owner=owner), ""
        doctor = chosen_doctor(slots, ctx)
        fee = doctor.get("fee") if doctor else None
        fee_part = " " + confirm.text("fee_part", lang, fee=money(fee, ctx, lang)) if fee else ""
        summary = confirm.text(
            "readback_book",
            lang,
            doctor=doctor_title(doctor, lang),
            pet=slots.get("pet_name", ""),
            owner=slots.get("owner_name", ""),
            when=self._when(slots, ctx, lang),
            serial_part=serial_part(slots.get("serial"), ctx, lang, confirm),
            fee_part=fee_part,
        )
        return summary, confirm.text("confirm_book", lang)

    # ---- commit ----------------------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        action = super().commit_core(branch, slots, ctx)
        if action is None or action.outcome != OUTCOME_BOOKED:
            return action
        pet = {key: slots[key] for key in PET_KEYS if slots.get(key) not in (None, "")}
        doctor = chosen_doctor(slots, ctx)
        species = f" ({slots['species']})" if slots.get("species") else ""
        action.fields = {
            **action.fields,
            # The record belongs to the owner (their name and number); the pet lives in the details.
            "customer_name": slots.get("owner_name", ""),
            "items_summary": f"{doctor.name if doctor else ''} — {slots.get('pet_name', '')}{species}".strip(" —"),
            "details": {**action.fields.get("details", {}), **pet},
        }
        return action

    # ---- prompt parts ----------------------------------------------------------------------------------
    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        return [*doctor_facts(ctx), f"Animal emergencies go to: {emergency_vet(ctx, 'en')}."]

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        return [*super().transcription_hints(ctx), "vaccination", "spay", "neuter", "deworming", "puppy", "kitten"]


__all__ = ["COMPACT_RULES", "RULES", "VetFlow"]
