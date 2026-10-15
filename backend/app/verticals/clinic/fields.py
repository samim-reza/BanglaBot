"""The clinic vertical's portal vocabulary and forms: records, doctors (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.clinic.catalog import KIND_APPOINTMENT, KIND_DOCTOR


def summarize(record: Any, names: dict[str, str]) -> str:
    doctor = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    details = getattr(record, "details", None)
    reason = details.get("reason", "") if isinstance(details, dict) else ""
    parts = [doctor or str(getattr(record, "items_summary", "") or ""), str(reason or "")]
    return " · ".join(part for part in parts if part)


#: Keyword arguments of the clinic :class:`~app.verticals.base.Vertical` (everything but its flows).
CLINIC_SPEC: dict[str, Any] = dict(
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
        FieldSpec("online", L("Offers online (video) visits", "অনলাইন (ভিডিও) সাক্ষাৎ দেন"), "bool"),
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
    outbound_label=L("Reminder call", "রিমাইন্ডার কল"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["CLINIC_SPEC", "summarize"]
