"""The clinic's call pipelines: which skills, in what order, per branch.

Inbound::

    greet → intent ─ book ───────▶ doctor → schedule → patient type* → patient details → phone
                   │                → visit mode* → payment* → approval* → read-back → book → text
                   ├ reschedule ─▶ find appointment → schedule → read-back → move
                   └ cancel ─────▶ find appointment → read-back → cancel
    (* off by default; the owner switches them on. Emergencies are handled at any point.)

Outbound reminder: identity → will you come? ─ no → another day? → schedule → read-back.
"""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.pipeline.blueprint import Blueprint, Branch
from app.skills.library.consent import ConsentSkill
from app.skills.library.customer_type import CustomerTypeSkill
from app.skills.library.emergency import EmergencySkill
from app.skills.library.greet import FarewellSkill, GreetSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.intent import IntentSkill
from app.skills.library.lines import L2, line
from app.skills.library.lookup import LookupSkill
from app.skills.library.notify import NotifySkill
from app.skills.library.payment import PaymentSkill
from app.skills.library.phone import PhoneSkill
from app.skills.library.schedule import ScheduleSkill
from app.skills.library.visit_mode import VisitModeSkill
from app.verticals.clinic.catalog import KIND_APPOINTMENT, chosen_doctor, doctor_availability, doctor_title
from app.verticals.clinic.flow import ClinicFlow
from app.verticals.clinic.skills import AttendSkill, ClinicConfirmSkill, DoctorSkill, NewTimeSkill, appointment_line

RED_FLAGS = (
    "chest pain", "breathing difficulty", "stroke signs", "heavy bleeding", "unconsciousness", "seizure",
    "severe injury", "pregnancy bleeding or severe pain", "poisoning",
)

PATIENT_FIELDS = (
    IntakeField("patient_name", L2("Patient name", "রোগীর নাম"), L2("May I have the patient's name?", "রোগীর নামটা বলবেন?"), required=True, long_answer=True, hint="May differ from the caller."),
    IntakeField("age", L2("Age", "বয়স"), L2("How old is the patient?", "রোগীর বয়স কত?"), type="number", on=False),
    IntakeField("dob", L2("Date of birth", "জন্মতারিখ"), L2("What is the patient's date of birth?", "রোগীর জন্মতারিখ কত?"), type="date", on=False),
    IntakeField("gender", L2("Gender", "লিঙ্গ"), L2("Is the patient male or female?", "রোগী পুরুষ না মহিলা?"), type="choice", choices=("male", "female", "other"), on=False),
    IntakeField("email", L2("Email", "ইমেইল"), L2("What email should we send the details to?", "কোন ইমেইলে বিস্তারিত পাঠাব?"), type="email", on=False),
    IntakeField("insurance", L2("Insurance", "বিমা"), L2("Do you have health insurance? If so, which provider?", "আপনার কি স্বাস্থ্য বিমা আছে? থাকলে কোন কোম্পানির?"), on=False),
    IntakeField("reason", L2("Reason for visit", "আসার কারণ"), L2("What is the visit for, briefly?", "কী সমস্যার জন্য আসছেন, সংক্ষেপে?"), ask=False, hint="A few words, only if the caller says it. Never ask for symptoms in detail."),
)

EMERGENCY_LINES = (
    line(
        "emergency",
        "This sounds like an emergency. Please call {emergency} right now, or take the patient to the nearest hospital emergency department.",
        "এটা জরুরি অবস্থা মনে হচ্ছে। দয়া করে এখনই {emergency} নম্বরে ফোন করুন, অথবা রোগীকে নিকটস্থ হাসপাতালের জরুরি বিভাগে নিয়ে যান।",
        label="Emergency line",
        variables=("emergency",),
        required=("emergency",),
    ),
)

SCHEDULE_LINES = (
    line("ask", "{who} sees patients {schedule}. Which day would you like to come?", "{who} {schedule} রোগী দেখেন। কোন দিন আসতে চান?", label="Ask for a day", variables=("who", "schedule")),
    line("ask_short", "Which day would you like?", "কোন দিন আসতে চান?", label="Ask again", static=True),
)


def _doctor_availability(slots: dict[str, Any], ctx: CallContext):  # noqa: ANN202
    return doctor_availability(chosen_doctor(slots, ctx), ctx)


def _who(slots: dict[str, Any], ctx: CallContext, language: str) -> str:
    return doctor_title(chosen_doctor(slots, ctx), language)


def _fee(slots: dict[str, Any], ctx: CallContext) -> Any:
    doctor = chosen_doctor(slots, ctx)
    return doctor.get("fee") if doctor else 0


def _describe(record: Any, ctx: CallContext, language: str) -> str:
    when, doctor, _ = appointment_line(record, ctx, language)
    return f"{when} {doctor}".strip()


def schedule_skill(needed) -> ScheduleSkill:  # noqa: ANN001
    return ScheduleSkill(
        availability=_doctor_availability,
        who=_who,
        notice_who=_who,
        needed=needed,
        lines=SCHEDULE_LINES,
        goal="Get the day they want to come (and a preferred time if they mention one).",
    )


def intent_skill() -> IntentSkill:
    return IntentSkill(
        {"book": "a new appointment", "reschedule": "move an existing appointment", "cancel": "cancel an existing appointment"},
        lines=(
            line("intent", "Would you like a new appointment, or to change or cancel an existing one?", "আপনি কি নতুন অ্যাপয়েন্টমেন্ট নিতে চান, নাকি আগের কোনো অ্যাপয়েন্টমেন্ট বদলাতে বা বাতিল করতে চান?", label="Ask what they need", static=True),
            line("branch_off", "Sorry, I can't do that over the phone, but the clinic team can help you.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, ক্লিনিকের টিম সাহায্য করবে।", label="Not offered by phone", static=True),
        ),
        goal="Find out whether they want a new appointment, to move one, or to cancel one (answer questions from the facts).",
    )


def patient_type_skill() -> CustomerTypeSkill:
    return CustomerTypeSkill(
        "patient_type",
        slot="patient_type",
        noun="patient",
        label=L2("New or existing patient", "নতুন না পুরনো রোগী"),
        lines=(line("ask", "Is this the patient's first visit with us, or have they been here before?", "রোগী কি প্রথমবার আসছেন, নাকি আগেও এসেছেন?", label="Ask new or existing", static=True),),
        goal="Find out whether the patient is new or has been here before.",
    )


def consent_skill() -> ConsentSkill:
    return ConsentSkill(
        lines=(
            line("terms", "Please note: if you can't come, let us know at least 24 hours before.", "দয়া করে মনে রাখবেন: আসতে না পারলে অন্তত ২৪ ঘণ্টা আগে জানাবেন।", label="Your terms", static=True),
            line("ask", "Do you agree?", "আপনি কি রাজি?", label="Ask to agree (own question)", static=True),
            line("declined", "No problem. Without that I can't book the appointment, but the clinic team can help you. Goodbye.", "ঠিক আছে। এটা ছাড়া অ্যাপয়েন্টমেন্ট দেওয়া যাচ্ছে না, ক্লিনিকের টিম সাহায্য করবে। ভালো থাকবেন।", label="If they don't agree", static=True),
        ),
        label=L2("Patient approval", "রোগীর সম্মতি"),
    )


def lookup_skill() -> LookupSkill:
    return LookupSkill(
        record_kind=KIND_APPOINTMENT,
        describe=_describe,
        slot="appointment",
        which_stage="which_appointment",
        none_stage="no_appointment_found",
        noun="appointment",
        lines=(
            line("which", "This number has {list} — which one do you mean?", "এই নম্বরে {list} আছে — কোনটার কথা বলছেন?", label="Ask which one", variables=("list",)),
            line("none", "Sorry, I can't find an appointment for this number. Would you like to book a new one?", "দুঃখিত, এই নম্বরে কোনো অ্যাপয়েন্টমেন্ট খুঁজে পাচ্ছি না। নতুন অ্যাপয়েন্টমেন্ট নিতে চান?", label="Nothing found", static=True),
        ),
        label=L2("Find the appointment", "অ্যাপয়েন্টমেন্ট খোঁজা"),
        goal="Find out which of the caller's appointments they mean.",
    )


def inbound_skills(fields: tuple[IntakeField, ...] = PATIENT_FIELDS) -> dict[str, Any]:
    """The inbound skill set; dental / vet reuse it with their own intake fields and wording."""
    skills = [
        GreetSkill(),
        FarewellSkill(),
        ClinicConfirmSkill(),
        intent_skill(),
        EmergencySkill(red_flags=RED_FLAGS, lines=EMERGENCY_LINES),
        DoctorSkill(),
        schedule_skill(lambda slots, ctx: slots.get("intent") in ("book", "reschedule")),
        patient_type_skill(),
        IntakeSkill(fields, label=L2("Patient details", "রোগীর তথ্য"), goal="Get the patient's details."),
        PhoneSkill(lines=(line("phone", "What is the patient's mobile number?", "রোগীর মোবাইল নম্বরটা বলবেন?", label="Ask for the number", static=True),), goal="Get the patient's mobile number."),
        VisitModeSkill(),
        PaymentSkill(amount=_fee),
        consent_skill(),
        lookup_skill(),
        NotifySkill(),
    ]
    return {skill.key: skill for skill in skills}


BOOK_BRANCH = Branch(
    "book",
    ("doctor", "schedule", "patient_type", "intake", "phone", "visit_mode", "payment", "consent"),
    label=L2("New appointment", "নতুন অ্যাপয়েন্টমেন্ট"),
    movable=(frozenset({"schedule", "patient_type", "intake", "phone"}), frozenset({"visit_mode", "payment"})),
    before={"schedule": frozenset({"doctor"}), "payment": frozenset({"doctor", "schedule"}), "consent": frozenset({"payment", "visit_mode"})},
    toggleable=False,
)


def inbound_blueprint(vertical: str, skills: dict[str, Any], flow_cls: type = ClinicFlow) -> Blueprint:
    return Blueprint(
        key=f"{vertical}.inbound",
        vertical=vertical,
        direction="inbound",
        skills=skills,
        prelude=("intent",),
        router_slot="intent",
        branches={
            "book": BOOK_BRANCH,
            "reschedule": Branch("reschedule", ("lookup", "schedule"), label=L2("Move an appointment", "অ্যাপয়েন্টমেন্ট বদল")),
            "cancel": Branch("cancel", ("lookup",), label=L2("Cancel an appointment", "অ্যাপয়েন্টমেন্ট বাতিল")),
        },
        default_branch="book",
        globals=("emergency",),
        effects=("notify",),
        line_skills=("greet", "farewell", "confirm"),
        flow_cls=flow_cls,
    )


def outbound_blueprint(vertical: str, emergency_lines=EMERGENCY_LINES, red_flags=RED_FLAGS, flow_cls: type = ClinicFlow, overrides: dict[str, Any] | None = None) -> Blueprint:  # noqa: ANN001
    """The reminder pipeline; ``overrides`` swaps skills by key (vet wording), ``flow_cls`` the flow."""
    skills = [
        FarewellSkill(),
        ClinicConfirmSkill(),
        AttendSkill(),
        NewTimeSkill(),
        schedule_skill(lambda slots, ctx: slots.get("wants_new_time") is True),
        EmergencySkill(red_flags=red_flags, lines=emergency_lines),
        NotifySkill(),
    ]
    return Blueprint(
        key=f"{vertical}.outbound",
        vertical=vertical,
        direction="outbound",
        skills={**{skill.key: skill for skill in skills}, **(overrides or {})},
        branches={"reminder": Branch("reminder", ("attend", "new_time", "schedule"), label=L2("Reminder", "রিমাইন্ডার"), toggleable=False)},
        default_branch="reminder",
        globals=("emergency",),
        effects=("notify",),
        line_skills=("farewell", "confirm"),
        flow_cls=flow_cls,
    )


INBOUND = inbound_blueprint("clinic", inbound_skills())
OUTBOUND = outbound_blueprint("clinic")
BLUEPRINTS = {"inbound": INBOUND, "outbound": OUTBOUND}

__all__ = [
    "BLUEPRINTS",
    "BOOK_BRANCH",
    "EMERGENCY_LINES",
    "INBOUND",
    "OUTBOUND",
    "PATIENT_FIELDS",
    "RED_FLAGS",
    "inbound_blueprint",
    "inbound_skills",
    "outbound_blueprint",
]
