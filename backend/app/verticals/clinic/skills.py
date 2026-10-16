"""Clinic-only skills: which doctor, the reminder questions, and the read-back / closing wording."""

from __future__ import annotations

from typing import Any

from app.flows.base import Instruction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import CONFIRMED, SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L, line
from app.verticals.clinic.catalog import (
    KIND_DOCTOR,
    departments,
    doctor_facts,
    doctor_title,
    record_serial,
    record_start,
    serial_words,
    uses_serials,
)
from app.verticals.common import join_and, when_phrase


class DoctorSkill(Skill):
    key = "doctor"
    label = L("Doctor")
    description = L("Finds the right doctor by name, department or problem; tells who's available.")
    toggleable = False
    slots = (SlotSpec("doctor", "The doctor, as the ref from the doctor list (D1, D2, …) — or the doctor's name / department if unsure."),)
    volunteerable = frozenset({"doctor"})
    lines = (
        line("doctor", "Which doctor would you like to see? We have {departments}.", label="Ask for a doctor", variables=("departments",)),
        line("choose", "We have {names} — who would you like to see?", label="Several match", variables=("names",)),
        line("unknown", "Sorry, I can't find that doctor. We have {departments}. Who would you like to see?", label="No match", variables=("departments",)),
    )
    goal = "Find out which doctor (save the D-ref)."

    def initial(self, b: BoundSkill, ctx: CallContext) -> dict[str, Any]:
        doctors = ctx.items(KIND_DOCTOR)
        if ctx.direction == DIRECTION_INBOUND and len(doctors) == 1:
            return {"doctor": doctors[0].ref}
        return {}

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        matches = ctx.find_items(fields["doctor"], KIND_DOCTOR, fields=("specialty",))
        if len(matches) == 1:
            fields["doctor"] = matches[0].ref
            return fields, None
        fields.pop("doctor")
        if matches:
            names = join_and([doctor_title(item, language) for item in matches[:4]], language)
            return fields, Instruction("doctor", b.text("choose", language, names=names), verbatim=True)
        return fields, Instruction("doctor", b.text("unknown", language, departments=departments(ctx, language)), verbatim=True)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("doctor", language, departments=departments(ctx, language))

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return doctor_facts(ctx)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("doctor", language, departments=departments(ctx, language))]


def appointment_line(record: Any, ctx: CallContext, language: str) -> tuple[str, str, str]:
    """(when, doctor, serial part) of an existing appointment."""
    item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
    start = record_start(record)
    when = when_phrase(start.astimezone(ctx.now.tzinfo), ctx, language, on=True) if start else ""
    return when, doctor_title(item, language), serial_part(record_serial(record), ctx, language, None)


def serial_part(serial: Any, ctx: CallContext, language: str, confirm: BoundSkill | None) -> str:
    if not serial or not uses_serials(ctx):
        return ""
    template = confirm.line_text("serial_part", language) if confirm else "Your queue number is {serial}."
    from app.skills.base import render

    return " " + render(template, {"serial": serial_words(serial, language)})


class AttendSkill(Skill):
    key = "attend"
    kind = "gate"
    label = L("Will they come?")
    toggleable = False
    slots = (SlotSpec("attend", "Outbound reminder: true = the patient will come, false = they cannot come.", {"type": "boolean"}, directions=("outbound",)),)
    gated = ("attend",)
    yes_no = {"attend": "attend"}
    lines = (
        line("attend", "You have an appointment with {doctor} {when}.{serial_part} Will you be able to make it?", label="Reminder question", variables=("doctor", "when", "serial_part")),
    )
    goal = "Will the patient come to this appointment?"

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return "attend" if slots.get("attend") is None else None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if saved.get("attend") is True:
            slots[CONFIRMED] = True

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        when, doctor, part = appointment_line(ctx.record, ctx, language)
        return b.text("attend", language, when=when, doctor=doctor, serial_part=part)


class NewTimeSkill(Skill):
    key = "new_time"
    kind = "gate"
    label = L("Another day?")
    toggleable = False
    slots = (SlotSpec("wants_new_time", "After saying they cannot come: true = they want another day, false = just cancel.", {"type": "boolean"}, directions=("outbound",)),)
    yes_no = {"wants_new_time": "wants_new_time"}
    lines = (line("new_time", "Alright. Would you like another day instead?", label="Offer another day", static=True),)
    goal = "They cannot come — would they like another day, or just cancel?"

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return slots.get("attend") is False

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return "wants_new_time" if slots.get("wants_new_time") is None else None

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("wants_new_time",)

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if saved.get("wants_new_time") is False:
            slots[CONFIRMED] = True  # "can't come" + "no other day": cancel without another read-back

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("new_time", language)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("new_time", language)]


class ClinicConfirmSkill(Skill):
    """Holds the read-back and closing wording (editable); the flow assembles them."""

    key = "confirm"
    kind = "line"
    toggleable = False
    label = L("Read-back and closing")
    description = L("What is read back before booking, and what is said after.")
    lines = (
        line("readback_book", "So that's {doctor} for {patient}, {when}.{serial_part}{fee_part}", label="Read-back (new)", variables=("doctor", "patient", "when", "serial_part", "fee_part")),
        line("confirm_book", "Shall I book it?", label="Confirm question (new)", static=True),
        line("readback_reschedule", "So I'll move your appointment with {doctor} to {when}.{serial_part}", label="Read-back (move)", variables=("doctor", "when", "serial_part")),
        line("confirm_reschedule", "Is that right?", label="Confirm question (move)", static=True),
        line("readback_cancel", "Shall I cancel {patient}'s appointment with {doctor}, {when}?", label="Read-back (cancel)", variables=("patient", "doctor", "when")),
        line("serial_part", "Your queue number is {serial}.", label="Queue number", variables=("serial",)),
        line("fee_part", "The consultation fee is {fee}.", label="Fee", variables=("fee",)),
        line("closing_booked", "Your appointment is booked for {when}.{serial_part} Please arrive a few minutes early.", label="After booking", variables=("when", "serial_part")),
        line("closing_rescheduled", "Your appointment is now {when}.{serial_part}", label="After moving", variables=("when", "serial_part")),
        line("closing_confirmed", "Thank you, your appointment is confirmed. Please come on time.", label="Reminder confirmed", static=True),
        line("closing_cancelled", "Alright, the appointment has been cancelled. Call us any time you need.", label="After cancelling", static=True),
        line("knows_person", "We have an appointment at our clinic under the name {name} for this number. Do you know them?", label="Someone else answered", variables=("name",)),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("closing_confirmed", language), b.text("closing_cancelled", language)]


__all__ = ["AttendSkill", "ClinicConfirmSkill", "DoctorSkill", "NewTimeSkill", "appointment_line", "serial_part"]
