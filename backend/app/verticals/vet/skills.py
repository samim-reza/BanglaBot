"""Vet-only wording and skills: the pet in the reminder question, the emergency vet, and the read-back / closings."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_EMERGENCY
from app.flows.context import CallContext
from app.skills.base import BoundSkill
from app.skills.library.emergency import EmergencySkill
from app.skills.library.lines import L, line
from app.verticals.clinic.skills import AttendSkill, ClinicConfirmSkill, appointment_line

#: Said when the account has not named its emergency vet.
DEFAULT_EMERGENCY_VET = {"en": "the nearest emergency vet"}


def pet_name(record: Any) -> str:
    details = getattr(record, "details", None)
    return str(details.get("pet_name") or "") if isinstance(details, dict) else ""


def emergency_vet(ctx: CallContext, language: str) -> str:
    configured = str(ctx.config.get("emergency_vet") or "").strip()
    return configured or DEFAULT_EMERGENCY_VET.get(language, DEFAULT_EMERGENCY_VET["en"])


class VetEmergencySkill(EmergencySkill):
    """Animal emergencies: go to the emergency vet now (the human emergency number is the wrong place)."""

    lines = (
        line(
            "emergency",
            "This sounds like an emergency. Please take your pet to {emergency_vet} right away.",
            label="Emergency line",
            variables=("emergency_vet", "emergency"),
            required=("emergency_vet",),
        ),
    )

    def closing(self, b: BoundSkill, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if outcome != OUTCOME_EMERGENCY:
            return ""
        return b.text("emergency", language, emergency_vet=emergency_vet(ctx, language), emergency=ctx.say_number(ctx.emergency_number, language))

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [self.closing(b, OUTCOME_EMERGENCY, {}, ctx, language)]


class VetAttendSkill(AttendSkill):
    """The reminder question names the pet."""

    lines = (
        line(
            "attend",
            "{pet} has an appointment with {doctor} {when}.{serial_part} Will you be able to make it?",
            label="Reminder question",
            variables=("pet", "doctor", "when", "serial_part"),
        ),
    )

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        when, doctor, part = appointment_line(ctx.record, ctx, language)
        pet = pet_name(ctx.record) or "Your pet"
        return b.text("attend", language, pet=pet, when=when, doctor=doctor, serial_part=part)


VET_CONFIRM_LINES = (
    line("readback_book", "So that's {doctor} for {pet}, {when}.{serial_part}{fee_part}", label="Read-back (new)", variables=("doctor", "pet", "owner", "when", "serial_part", "fee_part")),
    line("confirm_book", "Shall I book it?", label="Confirm question (new)", static=True),
    line("readback_reschedule", "So I'll move the appointment with {doctor} to {when}.{serial_part}", label="Read-back (move)", variables=("doctor", "when", "serial_part")),
    line("confirm_reschedule", "Is that right?", label="Confirm question (move)", static=True),
    line("readback_cancel", "Shall I cancel {pet}'s appointment with {doctor}, {when}?", label="Read-back (cancel)", variables=("pet", "owner", "doctor", "when")),
    line("serial_part", "Your queue number is {serial}.", label="Queue number", variables=("serial",)),
    line("fee_part", "The consultation fee is {fee}.", label="Fee", variables=("fee",)),
    line("closing_booked", "The appointment is booked for {when}.{serial_part} Please bring your pet on a leash or in a carrier.", label="After booking", variables=("when", "serial_part")),
    line("closing_rescheduled", "The appointment is now {when}.{serial_part}", label="After moving", variables=("when", "serial_part")),
    line("closing_confirmed", "Thank you, the appointment is confirmed. See you then.", label="Reminder confirmed", static=True),
    line("closing_cancelled", "Alright, the appointment has been cancelled. Call us any time you need.", label="After cancelling", static=True),
    line("knows_person", "We have a pet appointment at our clinic under the name {name} for this number. Do you know them?", label="Someone else answered", variables=("name",)),
)


def vet_confirm() -> ClinicConfirmSkill:
    return ClinicConfirmSkill(lines=VET_CONFIRM_LINES, description=L("What is read back before booking, and what is said after."))


__all__ = ["VET_CONFIRM_LINES", "VetAttendSkill", "VetEmergencySkill", "emergency_vet", "pet_name", "vet_confirm"]
