"""Vet-only wording and skills: the pet in the reminder question, the emergency vet, and the read-back / closings."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_EMERGENCY
from app.flows.context import CallContext
from app.skills.base import BoundSkill
from app.skills.library.emergency import EmergencySkill
from app.skills.library.lines import L2, line
from app.verticals.clinic.skills import AttendSkill, ClinicConfirmSkill, appointment_line

#: Said when the account has not named its emergency vet.
DEFAULT_EMERGENCY_VET = {"en": "the nearest emergency vet", "bn": "নিকটস্থ জরুরি পশু হাসপাতালে"}


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
            "এটা জরুরি অবস্থা মনে হচ্ছে। দয়া করে এখনই আপনার পোষা প্রাণীকে {emergency_vet} নিয়ে যান।",
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
            "{when} {doctor} এর কাছে {pet} এর অ্যাপয়েন্টমেন্ট আছে।{serial_part} আপনি কি আসছেন?",
            label="Reminder question",
            variables=("pet", "doctor", "when", "serial_part"),
        ),
    )

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        when, doctor, part = appointment_line(ctx.record, ctx, language)
        pet = pet_name(ctx.record) or ("আপনার পোষা প্রাণী" if language == "bn" else "Your pet")
        return b.text("attend", language, pet=pet, when=when, doctor=doctor, serial_part=part)


VET_CONFIRM_LINES = (
    line("readback_book", "So that's {doctor} for {pet}, {when}.{serial_part}{fee_part}", "তাহলে {pet} এর জন্য {when} {doctor} এর অ্যাপয়েন্টমেন্ট।{serial_part}{fee_part}", label="Read-back (new)", variables=("doctor", "pet", "owner", "when", "serial_part", "fee_part")),
    line("confirm_book", "Shall I book it?", "কনফার্ম করব?", label="Confirm question (new)", static=True),
    line("readback_reschedule", "So I'll move the appointment with {doctor} to {when}.{serial_part}", "তাহলে {doctor} এর অ্যাপয়েন্টমেন্টটা সরিয়ে {when} করে দিচ্ছি।{serial_part}", label="Read-back (move)", variables=("doctor", "when", "serial_part")),
    line("confirm_reschedule", "Is that right?", "ঠিক আছে?", label="Confirm question (move)", static=True),
    line("readback_cancel", "Shall I cancel {pet}'s appointment with {doctor}, {when}?", "{when} {doctor} এর সাথে {pet} এর অ্যাপয়েন্টমেন্টটা বাতিল করব?", label="Read-back (cancel)", variables=("pet", "owner", "doctor", "when")),
    line("serial_part", "Your queue number is {serial}.", "সিরিয়াল নম্বর {serial}।", label="Queue number", variables=("serial",)),
    line("fee_part", "The consultation fee is {fee}.", "ভিজিট ফি {fee}।", label="Fee", variables=("fee",)),
    line("closing_booked", "The appointment is booked for {when}.{serial_part} Please bring your pet on a leash or in a carrier.", "অ্যাপয়েন্টমেন্ট কনফার্ম হয়েছে — {when}।{serial_part} পোষা প্রাণীকে লিশে বা ক্যারিয়ারে করে আনবেন।", label="After booking", variables=("when", "serial_part")),
    line("closing_rescheduled", "The appointment is now {when}.{serial_part}", "অ্যাপয়েন্টমেন্ট {when} করা হয়েছে।{serial_part}", label="After moving", variables=("when", "serial_part")),
    line("closing_confirmed", "Thank you, the appointment is confirmed. See you then.", "ধন্যবাদ, অ্যাপয়েন্টমেন্ট কনফার্ম করা হলো। সময়মতো চলে আসবেন।", label="Reminder confirmed", static=True),
    line("closing_cancelled", "Alright, the appointment has been cancelled. Call us any time you need.", "ঠিক আছে, অ্যাপয়েন্টমেন্টটা বাতিল করা হলো। প্রয়োজনে আবার ফোন করবেন।", label="After cancelling", static=True),
    line("knows_person", "We have a pet appointment at our clinic under the name {name} for this number. Do you know them?", "এই নম্বরে {name} এর নামে আমাদের ক্লিনিকে একটি পোষা প্রাণীর অ্যাপয়েন্টমেন্ট আছে। আপনি কি ওনাকে চেনেন?", label="Someone else answered", variables=("name",)),
)


def vet_confirm() -> ClinicConfirmSkill:
    return ClinicConfirmSkill(lines=VET_CONFIRM_LINES, description=L2("What is read back before booking, and what is said after.", "বুকিংয়ের আগে যা পড়ে শোনানো হয় ও পরে যা বলা হয়।"))


__all__ = ["VET_CONFIRM_LINES", "VetAttendSkill", "VetEmergencySkill", "emergency_vet", "pet_name", "vet_confirm"]
