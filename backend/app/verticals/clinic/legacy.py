"""Clinic engine: doctor appointments (serials) for a chamber / clinic / diagnostic centre.

Inbound — the patient calls the clinic:

    intent ─ book ──────▶ doctor → patient_name → date → [phone] → read-back → book
           ├ reschedule ─▶ which appointment → date → read-back → move it
           └ cancel ─────▶ which appointment → read-back → cancel it
    (questions about doctors, fees, timings are answered from the catalog)

Outbound — the clinic calls a patient about an appointment (reminder):

    identity → attend? ─ yes → confirmed
                       └ no → new time? ─ yes → date → read-back → moved
                                        └ no → cancelled

A doctor sits on some weekdays for a session (e.g. Mon/Wed 17:00–21:00) cut
into slots of "minutes per patient". In South Asian chambers the slot's
position is the patient's *serial* (queue) number — said on the call when the
account uses queue numbers. The backend picks the slot nearest to the caller's
preferred time and reads it back; the model never invents availability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.flows.base import (
    STAGE_COMMIT,
    STAGE_DONE,
    OUTCOME_BOOKED,
    OUTCOME_CANCELLED,
    OUTCOME_CONFIRMED,
    OUTCOME_EMERGENCY,
    OUTCOME_RESCHEDULED,
    CommitAction,
    CommitResult,
    Instruction,
    Terminal,
)
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.flows.steps import CONFIRMED, STAGE_CONFIRM, SlotSpec, StepFlow, lang_text
from app.flows.timefmt import calendar_facts
from app.verticals.base import FieldSpec, L, Vertical
from app.verticals.common import (
    NOTICE,
    clear_notice,
    join_and,
    money,
    notice,
    plan_booking,
    schedule_phrase,
    slot_start,
    when_phrase,
    with_notice,
)
from app.verticals.reception import PHONE_HINT, caller_phone, clean_phone
from app.voice.languages import normalize_language, phrase

KIND_DOCTOR = "doctor"
KIND_APPOINTMENT = "appointment"

# --- stages --------------------------------------------------------------------
INTENT = "intent"
DOCTOR = "doctor"
PATIENT = "patient_name"
DATE = "date"
PHONE = "phone"
WHICH = "which_appointment"
NO_RECORD = "no_appointment_found"
ATTEND = "attend"
NEW_TIME = "wants_new_time"

_LINES: dict[str, dict[str, str]] = {
    "opening_question": {
        "bn": "আমি কীভাবে সাহায্য করতে পারি? ডাক্তারের অ্যাপয়েন্টমেন্ট নিতে চাইলে বলুন।",
        "en": "How can I help you today?",
    },
    "intent": {
        "bn": "আপনি কি নতুন অ্যাপয়েন্টমেন্ট নিতে চান, নাকি আগের কোনো অ্যাপয়েন্টমেন্ট বদলাতে বা বাতিল করতে চান?",
        "en": "Would you like a new appointment, or to change or cancel an existing one?",
    },
    "doctor": {
        "bn": "কোন ডাক্তার দেখাতে চান? আমাদের এখানে {departments} এর ডাক্তার আছেন।",
        "en": "Which doctor would you like to see? We have {departments}.",
    },
    "doctor_choose": {
        "bn": "আমাদের এখানে {names} আছেন — কার কাছে দেখাতে চান?",
        "en": "We have {names} — who would you like to see?",
    },
    "doctor_unknown": {
        "bn": "দুঃখিত, এই নামে কোনো ডাক্তার পাচ্ছি না। আমাদের এখানে {departments} এর ডাক্তার আছেন। কাকে দেখাতে চান?",
        "en": "Sorry, I can't find that doctor. We have {departments}. Who would you like to see?",
    },
    "patient_name": {
        "bn": "রোগীর নামটা বলবেন?",
        "en": "May I have the patient's name?",
    },
    "date": {
        "bn": "{doctor} {schedule} রোগী দেখেন। কোন দিন আসতে চান?",
        "en": "{doctor} sees patients {schedule}. Which day would you like to come?",
    },
    "date_short": {
        "bn": "কোন দিন আসতে চান?",
        "en": "Which day would you like?",
    },
    "phone": {
        "bn": "রোগীর মোবাইল নম্বরটা বলবেন?",
        "en": "What is the patient's mobile number?",
    },
    "readback_book": {
        "bn": "তাহলে {patient} এর জন্য {when} {doctor} এর অ্যাপয়েন্টমেন্ট।{serial_part}{fee_part} কনফার্ম করব?",
        "en": "So that's {doctor} for {patient}, {when}.{serial_part}{fee_part} Shall I book it?",
    },
    "readback_reschedule": {
        "bn": "তাহলে {doctor} এর অ্যাপয়েন্টমেন্টটা সরিয়ে {when} করে দিচ্ছি।{serial_part} ঠিক আছে?",
        "en": "So I'll move your appointment with {doctor} to {when}.{serial_part} Is that right?",
    },
    "serial_part": {
        "bn": " সিরিয়াল নম্বর {serial}।",
        "en": " Your queue number is {serial}.",
    },
    "fee_part": {
        "bn": " ভিজিট ফি {fee}।",
        "en": " The consultation fee is {fee}.",
    },
    "readback_cancel": {
        "bn": "{when} {doctor} এর সাথে {patient} এর অ্যাপয়েন্টমেন্টটা বাতিল করব?",
        "en": "Shall I cancel {patient}'s appointment with {doctor}, {when}?",
    },
    "which": {
        "bn": "এই নম্বরে {list} আছে — কোনটার কথা বলছেন?",
        "en": "This number has {list} — which one do you mean?",
    },
    "no_record": {
        "bn": "দুঃখিত, এই নম্বরে কোনো অ্যাপয়েন্টমেন্ট খুঁজে পাচ্ছি না। নতুন অ্যাপয়েন্টমেন্ট নিতে চান?",
        "en": "Sorry, I can't find an appointment for this number. Would you like to book a new one?",
    },
    "attend": {
        "bn": "{when} {doctor} এর কাছে আপনার অ্যাপয়েন্টমেন্ট আছে।{serial_part} আপনি কি আসছেন?",
        "en": "You have an appointment with {doctor} {when}.{serial_part} Will you be able to make it?",
    },
    "new_time": {
        "bn": "ঠিক আছে। অন্য কোনো দিনে অ্যাপয়েন্টমেন্ট নিতে চান?",
        "en": "Alright. Would you like another day instead?",
    },
    "closing_booked": {
        "bn": "আপনার অ্যাপয়েন্টমেন্ট কনফার্ম হয়েছে — {when}।{serial_part} একটু আগে চলে আসবেন। ধন্যবাদ, ভালো থাকবেন।",
        "en": "Your appointment is booked for {when}.{serial_part} Please arrive a few minutes early. Thank you, goodbye.",
    },
    "closing_rescheduled": {
        "bn": "আপনার অ্যাপয়েন্টমেন্ট {when} করা হয়েছে।{serial_part} ধন্যবাদ, ভালো থাকবেন।",
        "en": "Your appointment is now {when}.{serial_part} Thank you, goodbye.",
    },
    "closing_confirmed": {
        "bn": "ধন্যবাদ, আপনার অ্যাপয়েন্টমেন্ট কনফার্ম করা হলো। সময়মতো চলে আসবেন। ভালো থাকবেন।",
        "en": "Thank you, your appointment is confirmed. Please come on time. Goodbye.",
    },
    "closing_cancelled": {
        "bn": "ঠিক আছে, অ্যাপয়েন্টমেন্টটা বাতিল করা হলো। প্রয়োজনে আবার ফোন করবেন। ভালো থাকবেন।",
        "en": "Alright, the appointment has been cancelled. Call us any time you need. Goodbye.",
    },
    "emergency": {
        "bn": "এটা জরুরি অবস্থা মনে হচ্ছে। দয়া করে এখনই {emergency} নম্বরে ফোন করুন, অথবা রোগীকে নিকটস্থ হাসপাতালের জরুরি বিভাগে নিয়ে যান।",
        "en": "This sounds like an emergency. Please call {emergency} right now, or take the patient to the nearest hospital emergency department.",
    },
    "knows_person": {
        "bn": "এই নম্বরে {name} এর নামে আমাদের ক্লিনিকে একটি অ্যাপয়েন্টমেন্ট আছে। আপনি কি ওনাকে চেনেন?",
        "en": "We have an appointment at our clinic under the name {name} for this number. Do you know them?",
    },
}

_RULES = """You are the receptionist of a doctor's practice / clinic. You book doctor appointments and move or cancel existing ones. The system computes the appointment time (and queue number, where used).
- Never diagnose, never suggest medicines, tests or doses, never say whether a symptom is serious. For medical questions say the doctor will advise at the visit; if the facts list a health advice line, you may suggest it.
- Emergency (chest pain, breathing difficulty, stroke signs, heavy bleeding, unconsciousness, seizure, severe injury, pregnancy bleeding or severe pain, poisoning): call report_emergency immediately, nothing else.
- Never reveal another patient's details.
- Doctors: when saving `doctor`, use the ref from the doctor list (D1, D2, …). If the caller describes a problem instead of naming a doctor, you may name the matching department from the list (never diagnose); if several doctors fit, let the system ask.
- Intent: book = new appointment, reschedule = move an existing one, cancel = cancel an existing one. Questions about doctors, days, timings, fees or the address are answered from the facts below, then ask whether they would like an appointment.
- Dates: save `date` as YYYY-MM-DD from the calendar below ("tomorrow"/"কাল" = the next day, "the day after"/"পরশু" = two days ahead; a weekday means the next such day). A preferred time goes in `time_pref` as HH:MM (24 h) or morning/afternoon/evening.
- Existing appointments of this caller are listed with refs (A1, A2, …); save the chosen one as `appointment`.
- Availability: you never know which times are free — the system does. When the caller wants another day or time, save it (date / time_pref) and the system proposes the nearest free time; never say a time is or isn't available yourself.
- The system reads the summary back and writes the booking. Never say an appointment is booked, moved or cancelled before a tool result says so."""


# ------------------------------------------------------------------ catalog helpers
def doctor_availability(item: CatalogEntry | None, ctx: CallContext) -> Availability | None:
    if item is None:
        return None
    window = window_from_config(
        {
            "days": item.get("days") or [],
            "start": item.get("start_time"),
            "end": item.get("end_time"),
            "slot_minutes": item.get("slot_minutes") or 15,
            "max_patients": item.get("max_patients") or 0,
        },
        default_step=15,
    )
    if window is None:
        return None
    config = ctx.config
    return Availability(
        windows=[window],
        item_id=item.id,
        horizon_days=int(config.get("booking_horizon_days") or 14),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 30),
        busy=ctx.busy_for(item.id),
    )


def doctor_title(item: CatalogEntry | None, language: str) -> str:
    if item is None:
        return ""
    name = item.name.strip()
    lowered = name.lower()
    if lowered.startswith(("dr", "ডা", "ডাক্তার", "prof", "অধ্যাপক")):
        return name
    return f"ডা. {name}" if normalize_language(language) == "bn" else f"Dr. {name}"


def departments(ctx: CallContext, language: str) -> str:
    seen: list[str] = []
    for item in ctx.items(KIND_DOCTOR):
        specialty = str(item.get("specialty", "") or "").strip()
        if specialty and specialty not in seen:
            seen.append(specialty)
    return join_and(seen[:6], language) or join_and([doctor_title(i, language) for i in ctx.items(KIND_DOCTOR)][:4], language)


def _record_start(record: Any) -> datetime | None:
    value = getattr(record, "scheduled_at", None)
    return value if isinstance(value, datetime) else None


def _record_serial(record: Any) -> Any:
    details = getattr(record, "details", None)
    return details.get("serial") if isinstance(details, dict) else None


def uses_serials(ctx: CallContext) -> bool:
    """Queue (serial) numbers are said on the call: on for South Asian accounts unless switched off."""
    configured = ctx.config.get("queue_numbers")
    if isinstance(configured, bool):
        return configured
    return ctx.region.code in ("BD", "IN", "PK")


def _serial_words(value: Any, language: str) -> str:
    from app.flows.timefmt import bn_number

    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value or "")
    return bn_number(number) if normalize_language(language) == "bn" else str(number)


class ClinicFlow(StepFlow):
    vertical = "clinic"
    long_answer_stages = frozenset({PATIENT, PHONE})

    def __init__(self, direction: str) -> None:
        self.direction = direction
        self.key = f"clinic.{direction}"
        self.identity_gate = direction != DIRECTION_INBOUND

    # ---- slots ------------------------------------------------------------------
    slot_specs = (
        SlotSpec("intent", "What the caller wants — only once they say they want to book, move or cancel (not for a question).", {"type": "string", "enum": ["book", "reschedule", "cancel"]}, directions=('inbound',)),
        SlotSpec("doctor", "The doctor, as the ref from the doctor list (D1, D2, …) — or the doctor's name / department if unsure."),
        SlotSpec("patient_name", "The patient's name (may differ from the caller)."),
        SlotSpec("date", "Appointment date as YYYY-MM-DD. Convert a day the caller names ('tomorrow', 'Wednesday', 'next Monday') with the calendar in the facts."),
        SlotSpec("time_pref", "Preferred time: HH:MM (24 h) or morning / afternoon / evening. Only if the caller said one."),
        SlotSpec("phone", f"Patient's mobile number, digits only. {PHONE_HINT}"),
        SlotSpec("appointment", "Which existing appointment (ref A1, A2, … from the caller's appointments).", directions=('inbound',)),
        SlotSpec("reason", "Reason for the visit in a few words, only if the caller says it. Never ask for symptoms in detail."),
        SlotSpec("attend", "Outbound reminder: true = the patient will come, false = they cannot come.", {"type": "boolean"}, gated=True, directions=('outbound',)),
        SlotSpec("wants_new_time", "After saying they cannot come: true = they want another day, false = just cancel.", {"type": "boolean"}, directions=('outbound',)),
        SlotSpec("book_instead", "No appointment was found: true = they want a new one, false = no.", {"type": "boolean"}, directions=('inbound',)),
    )
    yes_no_stages = {STAGE_CONFIRM: CONFIRMED, ATTEND: "attend", NEW_TIME: "wants_new_time", NO_RECORD: "book_instead"}
    stage_goals = {
        INTENT: "Find out whether they want a new appointment, to move one, or to cancel one (answer questions from the facts).",
        DOCTOR: "Find out which doctor (save the D-ref).",
        PATIENT: "Get the patient's name.",
        DATE: "Get the day they want to come (and a preferred time if they mention one).",
        PHONE: "Get the patient's mobile number.",
        WHICH: "Find out which of the caller's appointments they mean.",
        NO_RECORD: "No appointment found for this number — do they want a new one?",
        ATTEND: "Will the patient come to this appointment?",
        NEW_TIME: "They cannot come — would they like another day, or just cancel?",
    }
    stage_slots = {
        INTENT: ("intent",),
        DOCTOR: ("doctor",),
        PATIENT: ("patient_name",),
        DATE: ("date", "time_pref"),
        PHONE: ("phone",),
        WHICH: ("appointment",),
        NO_RECORD: ("book_instead",),
        ATTEND: ("attend",),
        NEW_TIME: ("wants_new_time",),
    }

    @property
    def gated_slots(self) -> tuple[str, ...]:  # type: ignore[override]
        return ("attend", CONFIRMED)

    # ---- context helpers -----------------------------------------------------------
    def person_name(self, ctx: CallContext) -> str:
        return str(ctx.record_value("customer_name", ""))

    def _doctor(self, slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
        ref = slots.get("doctor")
        if ref:
            found = ctx.find_items(ref, KIND_DOCTOR)
            if len(found) == 1:
                return found[0]
        return None

    def confirms_cancellation(self, slots: dict[str, Any], ctx: CallContext) -> bool:
        return ctx.direction == DIRECTION_INBOUND and slots.get("intent") == "cancel"

    def _caller_appointments(self, ctx: CallContext) -> list[Any]:
        return [
            record
            for record in ctx.caller_records
            if str(getattr(record, "kind", "") or "") == KIND_APPOINTMENT and _record_start(record) is not None
        ]

    def _target(self, slots: dict[str, Any], ctx: CallContext) -> Any | None:
        if ctx.direction != DIRECTION_INBOUND:
            return ctx.record
        wanted = str(slots.get("appointment") or "")
        for index, record in enumerate(self._caller_appointments(ctx), start=1):
            if wanted in (f"A{index}", str(getattr(record, "id", ""))):
                return record
        return None

    # ---- initial / normalize / derive ----------------------------------------------
    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        doctors = ctx.items(KIND_DOCTOR)
        if ctx.direction == DIRECTION_INBOUND:
            if len(doctors) == 1:
                slots["doctor"] = doctors[0].ref
            return slots
        # Outbound: the appointment's doctor and patient are known.
        record = ctx.record
        item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
        if item is not None:
            slots["doctor"] = item.ref
        if record is not None:
            slots["patient_name"] = getattr(record, "customer_name", "")
        return slots

    def normalize(self, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        fields = dict(fields)
        lang = normalize_language(language)
        if "doctor" in fields:
            matches = ctx.find_items(fields["doctor"], KIND_DOCTOR, fields=("specialty",))
            if len(matches) == 1:
                fields["doctor"] = matches[0].ref
            else:
                fields.pop("doctor")
                if matches:
                    names = join_and([doctor_title(item, lang) for item in matches[:4]], lang)
                    line = lang_text(_LINES["doctor_choose"], lang).format(names=names)
                else:
                    line = lang_text(_LINES["doctor_unknown"], lang).format(departments=departments(ctx, lang))
                return fields, Instruction(DOCTOR, line, verbatim=True)
        if "phone" in fields:
            phone = clean_phone(fields["phone"])
            if not phone:
                fields.pop("phone")
                return fields, Instruction(PHONE, phrase("phone_invalid", lang), verbatim=True)
            fields["phone"] = phone
        if "appointment" in fields:
            wanted = str(fields["appointment"]).strip().upper()
            refs = {f"A{index}" for index in range(1, len(self._caller_appointments(ctx)) + 1)}
            if wanted not in refs:
                fields.pop("appointment")
        return fields, None

    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        clear_notice(slots)
        super().on_saved(saved, slots, ctx)
        if saved.get("book_instead") is True:
            slots["intent"] = "book"
        if saved.get("attend") is True:
            slots[CONFIRMED] = True

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        if ctx.direction == DIRECTION_INBOUND and slots.get("intent") in ("cancel", "reschedule") and not slots.get("appointment"):
            if len(self._caller_appointments(ctx)) == 1:
                slots["appointment"] = "A1"
        if slots.get("appointment") and slots.get("intent") == "reschedule":
            # Moving an appointment keeps its doctor.
            target = self._target(slots, ctx)
            item = ctx.item_by_id(getattr(target, "catalog_item_id", None))
            if item is not None:
                slots["doctor"] = item.ref
        needs_slot = (
            slots.get("intent") in ("book", "reschedule")
            if ctx.direction == DIRECTION_INBOUND
            else slots.get("wants_new_time") is True
        )
        if not needs_slot:
            for key in ("slot", "serial"):
                slots.pop(key, None)
            return
        doctor = self._doctor(slots, ctx)
        plan_booking(slots, ctx, doctor_availability(doctor, ctx), who=doctor_title(doctor, "bn"))

    # ---- the cascade -----------------------------------------------------------------
    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        gate = self.identity_stage(slots)
        if gate is not None:
            return gate
        if ctx.direction == DIRECTION_INBOUND:
            return self._inbound_stage(slots, ctx)
        return self._outbound_stage(slots, ctx)

    def _inbound_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        if slots.get("decision"):
            return self.tail(slots)
        intent = slots.get("intent")
        if not intent:
            return INTENT
        if intent in ("cancel", "reschedule"):
            mine = self._caller_appointments(ctx)
            if not mine:
                if slots.get("book_instead") is None:
                    return NO_RECORD
                return STAGE_DONE if slots.get("book_instead") is False else INTENT
            if not slots.get("appointment"):
                return WHICH
            if intent == "cancel":
                return self.tail(slots)
            if not slots.get("date") or not slots.get("slot"):
                return DATE
            return self.tail(slots)
        # book: doctor → day (checked against the doctor's schedule) → patient → phone
        if not slots.get("doctor"):
            return DOCTOR
        if not slots.get("date") or not slots.get("slot"):
            return DATE
        if not slots.get("patient_name"):
            return PATIENT
        if not caller_phone(slots, ctx):
            return PHONE
        return self.tail(slots)

    def _outbound_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        if slots.get("decision"):
            return self.tail(slots)
        attend = slots.get("attend")
        if attend is None:
            return ATTEND
        if attend is True:
            return self.tail(slots)
        wants = slots.get("wants_new_time")
        if wants is None:
            return NEW_TIME
        if wants is False:
            # "Can't come" + "no other day": cancel without another read-back.
            return STAGE_COMMIT
        if not slots.get("date") or not slots.get("slot"):
            return DATE
        return self.tail(slots)

    # ---- lines --------------------------------------------------------------------------
    def opening_question(self, ctx: CallContext, language: str) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return lang_text(_LINES["opening_question"], language)
        return super().opening_question(ctx, language)

    def greeting(self, ctx: CallContext, language: str) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return self.inbound_greeting(ctx, language)
        return super().greeting(ctx, language)

    def knows_person_line(self, ctx: CallContext, language: str) -> str:
        return lang_text(_LINES["knows_person"], language).format(name=self.person_name(ctx))

    def _when(self, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        start = slot_start(slots)
        return when_phrase(start, ctx, language) if start else ""

    def _record_when(self, record: Any, ctx: CallContext, language: str) -> str:
        start = _record_start(record)
        if start is None:
            return ""
        return when_phrase(start.astimezone(ctx.now.tzinfo), ctx, language, on=True)

    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        lang = normalize_language(language)
        line = self._stage_text(stage, slots, ctx, lang)
        if isinstance(line, Instruction):
            return line
        return with_notice(slots, ctx, lang, line)

    def _stage_text(self, stage: str, slots: dict[str, Any], ctx: CallContext, lang: str) -> Instruction | str:
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        doctor = self._doctor(slots, ctx)
        if stage == INTENT:
            return t("intent")
        if stage == DOCTOR:
            return t("doctor").format(departments=departments(ctx, lang))
        if stage == PATIENT:
            return t("patient_name")
        if stage == DATE:
            if slots.get(NOTICE):
                # The notice already said which days work.
                return t("date_short")
            availability = doctor_availability(doctor, ctx)
            schedule = schedule_phrase(availability, lang, ctx) if availability else ""
            return t("date").format(doctor=doctor_title(doctor, lang), schedule=schedule)
        if stage == PHONE:
            return t("phone")
        if stage == WHICH:
            items = [
                f"{self._record_when(record, ctx, lang)} {doctor_title(ctx.item_by_id(getattr(record, 'catalog_item_id', None)), lang)}".strip()
                for record in self._caller_appointments(ctx)[:3]
            ]
            return t("which").format(list=join_and(items, lang))
        if stage == NO_RECORD:
            return t("no_record")
        if stage == ATTEND:
            record = ctx.record
            item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
            return t("attend").format(
                when=self._record_when(record, ctx, lang),
                doctor=doctor_title(item, lang),
                serial_part=self._serial_part(_record_serial(record), ctx, lang),
            )
        if stage == NEW_TIME:
            return t("new_time")
        if stage == STAGE_CONFIRM:
            return self._readback(slots, ctx, lang)
        return ""

    def _readback(self, slots: dict[str, Any], ctx: CallContext, lang: str) -> str:
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        intent = self._intent(slots, ctx)
        doctor = self._doctor(slots, ctx)
        if intent == "cancel":
            target = self._target(slots, ctx)
            item = ctx.item_by_id(getattr(target, "catalog_item_id", None))
            return t("readback_cancel").format(
                when=self._record_when(target, ctx, lang),
                doctor=doctor_title(item, lang),
                patient=getattr(target, "customer_name", "") or "",
            )
        when = self._when(slots, ctx, lang)
        serial_part = self._serial_part(slots.get("serial"), ctx, lang)
        if intent == "reschedule":
            return t("readback_reschedule").format(doctor=doctor_title(doctor, lang), when=when, serial_part=serial_part)
        fee = doctor.get("fee") if doctor else None
        return t("readback_book").format(
            patient=slots.get("patient_name", ""),
            when=when,
            doctor=doctor_title(doctor, lang),
            serial_part=serial_part,
            # No fee on file: drop the fee sentence rather than invent one.
            fee_part=t("fee_part").format(fee=money(fee, ctx, lang)) if fee else "",
        )

    def _serial_part(self, serial: Any, ctx: CallContext, lang: str) -> str:
        if not serial or not uses_serials(ctx):
            return ""
        return lang_text(_LINES["serial_part"], lang).format(serial=_serial_words(serial, lang))

    def _intent(self, slots: dict[str, Any], ctx: CallContext) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return str(slots.get("intent") or "book")
        if slots.get("attend") is True:
            return "confirm"
        if slots.get("wants_new_time") is False:
            return "cancel"
        return "reschedule"

    # ---- commit -----------------------------------------------------------------------
    def commit_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        intent = self._intent(slots, ctx)
        doctor = self._doctor(slots, ctx)
        target = self._target(slots, ctx)
        if intent == "confirm":
            return CommitAction(outcome=OUTCOME_CONFIRMED, status="confirmed", record_id=str(getattr(target, "id", "") or "") or None)
        if intent == "cancel":
            if target is None:
                return None
            return CommitAction(outcome=OUTCOME_CANCELLED, status="cancelled", record_id=str(getattr(target, "id", "")))
        start = slot_start(slots)
        if doctor is None or start is None:
            return None
        details = {
            "serial": int(slots.get("serial") or 1),
            "doctor": doctor.name,
            "specialty": doctor.get("specialty", ""),
        }
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
        doctor = self._doctor(slots, ctx)
        if start is not None:
            ctx.mark_booked(doctor.id if doctor else None, start, 99)
        slots[CONFIRMED] = None
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- terminals / closings -------------------------------------------------------------
    def terminals(self) -> list[Terminal]:
        return [
            Terminal(
                name="report_emergency",
                outcome=OUTCOME_EMERGENCY,
                description=(
                    "The caller describes a medical emergency (chest pain, breathing difficulty, stroke signs, heavy "
                    "bleeding, unconsciousness, seizure, severe injury, pregnancy emergency, poisoning). Call at once."
                ),
                properties={"what": {"type": "string", "description": "What the caller described, a few words."}},
                note_template={"bn": "জরুরি অবস্থা: {what}", "en": "Emergency: {what}"},
                requires_identity=False,
            )
        ]

    def closing_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        when = self._when(slots, ctx, lang)
        serial_part = self._serial_part(slots.get("serial"), ctx, lang)
        if outcome == OUTCOME_BOOKED:
            return t("closing_booked").format(when=when, serial_part=serial_part)
        if outcome == OUTCOME_RESCHEDULED:
            return t("closing_rescheduled").format(when=when, serial_part=serial_part)
        if outcome == OUTCOME_CONFIRMED:
            return t("closing_confirmed")
        if outcome == OUTCOME_CANCELLED:
            return t("closing_cancelled")
        if outcome == OUTCOME_EMERGENCY:
            return t("emergency").format(emergency=ctx.say_number(ctx.emergency_number, lang))
        return super().closing_line(outcome, slots, ctx, lang)

    # ---- prompt parts ------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return _RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = ["Doctors (ref: name — department, degrees, days, hours, minutes per patient, fee):"]
        for item in ctx.items(KIND_DOCTOR):
            availability = doctor_availability(item, ctx)
            schedule = schedule_phrase(availability, "en", ctx) if availability else "schedule not set"
            parts = [f"{item.ref}: {item.name}"]
            if item.get("specialty"):
                parts.append(f"— {item.get('specialty')}")
            if item.get("degrees"):
                parts.append(f"({item.get('degrees')})")
            parts.append(f"; {schedule}")
            if item.get("slot_minutes"):
                parts.append(f"; ~{item.get('slot_minutes')} min per patient")
            if item.get("fee"):
                parts.append(f"; fee {item.get('fee')} {ctx.currency}")
            if item.get("notes"):
                parts.append(f"; {item.get('notes')}")
            lines.append("- " + " ".join(parts))
        if len(lines) == 1:
            lines.append("- (no doctors added yet — take a message: say the clinic will call back)")
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
            mine = self._caller_appointments(ctx)
            if mine:
                lines.append("This caller's upcoming appointments:")
                for index, record in enumerate(mine, start=1):
                    start = _record_start(record)
                    item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
                    stamp = start.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M") if start else "?"
                    lines.append(
                        f"- A{index}: {stamp} with {item.name if item else '?'} for {getattr(record, 'customer_name', '')}"
                        f", serial {_record_serial(record) or '?'}"
                    )
        else:
            record = ctx.record
            item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
            start = _record_start(record)
            stamp = start.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M") if start else "?"
            lines.append(
                f"This call is a reminder about {self.person_name(ctx)}'s appointment: {stamp} with "
                f"{item.name if item else '?'}, serial {_record_serial(record) or '?'}."
            )
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [item.name for item in ctx.items(KIND_DOCTOR)][:8]
        hints += ["সিরিয়াল", "অ্যাপয়েন্টমেন্ট", "ডাক্তার"]
        if ctx.record is not None:
            hints.append(self.person_name(ctx))
        return hints

    # ---- prefetch / preview ------------------------------------------------------------------
    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        lines = super().prefetch_lines(ctx, lang) + [
            t("intent"),
            t("patient_name"),
            t("phone"),
            t("no_record"),
            t("new_time"),
            t("closing_confirmed"),
            t("closing_cancelled"),
            t("emergency").format(emergency=ctx.say_number(ctx.emergency_number, lang)),
            phrase("amend_question", lang),
            phrase("phone_invalid", lang),
            phrase("closing_inquiry", lang),
            t("doctor").format(departments=departments(ctx, lang)),
        ]
        for item in ctx.items(KIND_DOCTOR)[:6]:
            availability = doctor_availability(item, ctx)
            if availability:
                lines.append(t("date").format(doctor=doctor_title(item, lang), schedule=schedule_phrase(availability, lang, ctx)))
        return lines

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        if ctx.direction == DIRECTION_INBOUND:
            if lang == "bn":
                return [
                    f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                    "ডাক্তার: কোন ডাক্তার/বিভাগ — আপনার ডাক্তার তালিকা থেকে।",
                    "রোগীর নাম ও দিন: ডাক্তারের বসার দিন অনুযায়ী তারিখ যাচাই, পছন্দের সময়ের কাছাকাছি সিরিয়াল।",
                    "পড়ে শোনানো: ডাক্তার, দিন, সময়, সিরিয়াল নম্বর ও ফি — 'হ্যাঁ' বললে বুক হয়।",
                    "বাতিল / সময় বদল: কলারের নম্বরের অ্যাপয়েন্টমেন্ট খুঁজে বাতিল বা নতুন সময়।",
                    f"জরুরি অবস্থা: {ctx.emergency_number}-এ ফোন করতে বলা হয়; কোনো চিকিৎসা পরামর্শ দেওয়া হয় না।",
                ]
            return [
                f"Greeting: \"{self.opening(ctx, lang)}\"",
                "Doctor: which doctor / department — from your doctor list.",
                "Patient name and day: the day is checked against the doctor's schedule; the free slot nearest the preferred time is picked.",
                "Read-back: doctor, day, time (and queue number where used) and fee — booked on a 'yes'.",
                "Cancel / reschedule: finds the caller's appointment by phone number.",
                f"Emergencies: told to call {ctx.emergency_number}; no medical advice is ever given.",
            ]
        if lang == "bn":
            return [
                f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                "রিমাইন্ডার: অ্যাপয়েন্টমেন্টের দিন, সময় ও সিরিয়াল বলে জিজ্ঞেস করে আসবেন কি না।",
                "না আসলে: অন্য দিনে সিরিয়াল দেয়, না চাইলে বাতিল করে।",
            ]
        return [
            f"Greeting: \"{self.opening(ctx, lang)}\"",
            "Reminder: states the appointment day and time and asks whether they will come.",
            "If not: offers another day, otherwise cancels.",
        ]


INBOUND = ClinicFlow(DIRECTION_INBOUND)
OUTBOUND = ClinicFlow("outbound")


def _summary(record: Any, names: dict[str, str]) -> str:
    doctor = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    details = getattr(record, "details", None)
    reason = details.get("reason", "") if isinstance(details, dict) else ""
    parts = [doctor or str(getattr(record, "items_summary", "") or ""), str(reason or "")]
    return " · ".join(part for part in parts if part)


CLINIC = Vertical(
    key="clinic",
    label=L("Doctor appointments", "ডাক্তারের অ্যাপয়েন্টমেন্ট"),
    description=L(
        "Answers the clinic's phone: books doctor appointments, moves or cancels appointments, answers questions about doctors, days and fees, and calls patients with reminders.",
        "ক্লিনিকের ফোন ধরে: ডাক্তারের সিরিয়াল দেয়, অ্যাপয়েন্টমেন্ট বদলায় বা বাতিল করে, ডাক্তার-দিন-ফি নিয়ে প্রশ্নের উত্তর দেয়, আর রোগীদের রিমাইন্ডার কল করে।",
    ),
    record_kind=KIND_APPOINTMENT,
    record_label=L("Appointment", "অ্যাপয়েন্টমেন্ট"),
    record_label_plural=L("Appointments", "অ্যাপয়েন্টমেন্ট"),
    record_fields=(
        FieldSpec("customer_name", L("Patient name", "রোগীর নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Doctor", "ডাক্তার"), "catalog", required=True, list_column=True),
        FieldSpec("scheduled_at", L("Date & time", "দিন ও সময়"), "datetime", required=True, list_column=True),
        FieldSpec("serial", L("Queue / serial no.", "সিরিয়াল নম্বর"), "number"),
        FieldSpec("reason", L("Reason", "কারণ"), "text"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_DOCTOR,
    catalog_label=L("Doctor", "ডাক্তার"),
    catalog_label_plural=L("Doctors", "ডাক্তার"),
    catalog_fields=(
        FieldSpec("name", L("Doctor's name", "ডাক্তারের নাম"), required=True, placeholder="Dr. Abdul Karim"),
        FieldSpec("specialty", L("Department / specialty", "বিভাগ"), required=True, placeholder="Medicine / শিশু রোগ"),
        FieldSpec("degrees", L("Degrees", "ডিগ্রি"), placeholder="MBBS, FCPS (Medicine)"),
        FieldSpec("days", L("Chamber days", "বসার দিন"), "days", required=True),
        FieldSpec("start_time", L("Starts at", "শুরু"), "time", required=True, default="17:00"),
        FieldSpec("end_time", L("Ends at", "শেষ"), "time", required=True, default="21:00"),
        FieldSpec(
            "slot_minutes",
            L("Minutes per patient", "প্রতি রোগী (মিনিট)"),
            "number",
            default=15,
            help=L("Serial n arrives at start + (n − 1) × this.", "সিরিয়াল n এর সময় = শুরু + (n − ১) × এই মিনিট।"),
        ),
        FieldSpec("max_patients", L("Max patients per day", "দিনে সর্বোচ্চ রোগী"), "number", default=0, help=L("0 = no limit", "০ = সীমা নেই")),
        FieldSpec("fee", L("Consultation fee", "ভিজিট ফি"), "money"),
        FieldSpec("notes", L("Notes for the agent", "এজেন্টের জন্য নোট"), "textarea", placeholder="Room 304. Reports shown free within 7 days."),
        FieldSpec(
            "calendar_ics",
            L("Busy calendar (iCal link)", "ব্যস্ত সময়ের ক্যালেন্ডার (iCal লিংক)"),
            placeholder="https://calendar.google.com/calendar/ical/…/basic.ics",
            help=L(
                "Optional. The doctor's private iCal address (Google Calendar → Settings → Secret address in iCal format). Busy times are never offered.",
                "ঐচ্ছিক। ডাক্তারের ক্যালেন্ডারের গোপন iCal ঠিকানা — ব্যস্ত সময়ে সিরিয়াল দেওয়া হবে না।",
            ),
        ),
    ),
    config_fields=(
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=14),
        FieldSpec("lead_minutes", L("Earliest booking (minutes from now)", "এখন থেকে অন্তত কত মিনিট পরে"), "number", default=30),
        FieldSpec(
            "queue_numbers",
            L("Tell patients a queue (serial) number", "রোগীকে সিরিয়াল নম্বর বলা হবে"),
            "bool",
            help=L("Common in South Asian chambers. Unset = on for BD/IN/PK accounts.", "দক্ষিণ এশিয়ার চেম্বারে প্রচলিত।"),
        ),
        FieldSpec(
            "health_line",
            L("Health advice line (optional)", "স্বাস্থ্য পরামর্শ লাইন (ঐচ্ছিক)"),
            placeholder="111 (NHS)",
            help=L("Suggested for medical questions; empty = the region's line, if any.", "চিকিৎসা প্রশ্নে বলা হয়; খালি = অঞ্চলের লাইন।"),
        ),
    ),
    config_defaults={"booking_horizon_days": 14, "lead_minutes": 30},
    status_labels={
        "pending": L("Scheduled", "নির্ধারিত"),
        "confirmed": L("Confirmed", "কনফার্মড"),
        "cancelled": L("Cancelled", "বাতিল"),
        "needs_review": L("Needs review", "রিভিউ দরকার"),
    },
    flows={"inbound": INBOUND, "outbound": OUTBOUND},
    outbound_label=L("Reminder call", "রিমাইন্ডার কল"),
    scheduled=True,
    summarize=_summary,
)

__all__ = ["CLINIC", "ClinicFlow", "doctor_availability", "doctor_title"]
