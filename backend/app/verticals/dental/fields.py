"""The dental vertical's portal vocabulary and forms: appointments, dentists (catalog), settings.

Dentists are stored as the clinic engine's ``doctor`` catalog kind, so every clinic
helper (schedules, queue numbers, read-backs) works unchanged; only the words differ.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.clinic.catalog import KIND_APPOINTMENT, KIND_DOCTOR
from app.verticals.clinic.fields import CLINIC_SPEC, summarize

_RELABEL = {
    "name": dict(label=L("Dentist's name", "ডেন্টিস্টের নাম"), placeholder="Dr. Emily Park"),
    "specialty": dict(label=L("Specialty", "বিশেষত্ব"), placeholder="General dentistry / Orthodontics"),
    "days": dict(label=L("Working days", "কাজের দিন")),
    "start_time": dict(default="09:00"),
    "end_time": dict(default="17:00"),
    "slot_minutes": dict(default=30),
    "fee": dict(label=L("Exam / consultation fee", "পরামর্শ ফি")),
}


def _catalog_fields() -> tuple[FieldSpec, ...]:
    return tuple(replace(spec, **_RELABEL.get(spec.key, {})) for spec in CLINIC_SPEC["catalog_fields"] if spec.key != "online")


#: Keyword arguments of the dental :class:`~app.verticals.base.Vertical` (everything but its flows).
DENTAL_SPEC: dict[str, Any] = dict(
    key="dental",
    label=L("Dental appointments", "ডেন্টাল অ্যাপয়েন্টমেন্ট"),
    description=L(
        "Answers the dental practice's phone: books check-ups, cleanings and treatment visits, moves or cancels appointments, takes the patient's insurance, and calls patients with reminders.",
        "ডেন্টাল চেম্বারের ফোন ধরে: চেকআপ, ক্লিনিং ও চিকিৎসার অ্যাপয়েন্টমেন্ট দেয়, বদলায় বা বাতিল করে, বিমার তথ্য নেয়, আর রোগীদের রিমাইন্ডার কল করে।",
    ),
    record_kind=KIND_APPOINTMENT,
    record_label=L("Appointment", "অ্যাপয়েন্টমেন্ট"),
    record_label_plural=L("Appointments", "অ্যাপয়েন্টমেন্ট"),
    record_fields=(
        FieldSpec("customer_name", L("Patient name", "রোগীর নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Dentist", "ডেন্টিস্ট"), "catalog", required=True, list_column=True),
        FieldSpec("scheduled_at", L("Date & time", "দিন ও সময়"), "datetime", required=True, list_column=True),
        FieldSpec("reason", L("Reason", "কারণ"), "text", placeholder="Cleaning / check-up / toothache"),
        FieldSpec("insurance", L("Insurance", "বিমা"), "text"),
        FieldSpec("serial", L("Queue / serial no.", "সিরিয়াল নম্বর"), "number"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_DOCTOR,
    catalog_label=L("Dentist", "ডেন্টিস্ট"),
    catalog_label_plural=L("Dentists", "ডেন্টিস্ট"),
    catalog_fields=_catalog_fields(),
    config_fields=tuple(spec for spec in CLINIC_SPEC["config_fields"] if spec.key != "health_line"),
    config_defaults={"booking_horizon_days": 30, "lead_minutes": 60},
    status_labels=dict(CLINIC_SPEC["status_labels"]),
    outbound_label=L("Reminder call", "রিমাইন্ডার কল"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["DENTAL_SPEC"]
