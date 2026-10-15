"""The vet vertical's portal vocabulary and forms: appointments (owner + pet), vets (catalog), settings.

Vets are stored as the clinic engine's ``doctor`` catalog kind, so every clinic helper works unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.clinic.catalog import KIND_APPOINTMENT, KIND_DOCTOR
from app.verticals.clinic.fields import CLINIC_SPEC

_RELABEL = {
    "name": dict(label=L("Vet's name", "ভেটের নাম"), placeholder="Dr. Sam Rivera, DVM"),
    "specialty": dict(label=L("Specialty", "বিশেষত্ব"), placeholder="General practice / Exotics / Surgery"),
    "days": dict(label=L("Working days", "কাজের দিন")),
    "start_time": dict(default="09:00"),
    "end_time": dict(default="17:00"),
    "slot_minutes": dict(label=L("Minutes per appointment", "প্রতি অ্যাপয়েন্টমেন্ট (মিনিট)"), default=20),
    "max_patients": dict(label=L("Max appointments per day", "দিনে সর্বোচ্চ অ্যাপয়েন্টমেন্ট")),
}

SPECIES_OPTIONS = tuple(
    (key, L(en, bn))
    for key, en, bn in (("dog", "Dog", "কুকুর"), ("cat", "Cat", "বিড়াল"), ("bird", "Bird", "পাখি"), ("rabbit", "Rabbit", "খরগোশ"), ("other", "Other", "অন্যান্য"))
)


def summarize(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    vet = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    pet = " ".join(str(details.get(key) or "") for key in ("pet_name", "species")).strip() if isinstance(details, dict) else ""
    reason = details.get("reason", "") if isinstance(details, dict) else ""
    return " · ".join(part for part in (pet, vet, str(reason or "")) if part)


#: Keyword arguments of the vet :class:`~app.verticals.base.Vertical` (everything but its flows).
VET_SPEC: dict[str, Any] = dict(
    key="vet",
    label=L("Vet clinic", "পশু চিকিৎসা ক্লিনিক"),
    description=L(
        "Answers the vet clinic's phone: books appointments for pets, moves or cancels them, sends animal emergencies to the emergency vet, and calls owners with reminders.",
        "পশু ক্লিনিকের ফোন ধরে: পোষা প্রাণীর অ্যাপয়েন্টমেন্ট দেয়, বদলায় বা বাতিল করে, জরুরি অবস্থায় জরুরি পশু হাসপাতালে পাঠায়, আর মালিকদের রিমাইন্ডার কল করে।",
    ),
    record_kind=KIND_APPOINTMENT,
    record_label=L("Appointment", "অ্যাপয়েন্টমেন্ট"),
    record_label_plural=L("Appointments", "অ্যাপয়েন্টমেন্ট"),
    record_fields=(
        FieldSpec("customer_name", L("Owner's name", "মালিকের নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("pet_name", L("Pet's name", "পোষা প্রাণীর নাম"), required=True, list_column=True),
        FieldSpec("species", L("Species", "প্রাণীর ধরন"), "select", options=SPECIES_OPTIONS),
        FieldSpec("catalog_item_id", L("Vet", "ভেট"), "catalog", required=True, list_column=True),
        FieldSpec("scheduled_at", L("Date & time", "দিন ও সময়"), "datetime", required=True, list_column=True),
        FieldSpec("reason", L("Reason", "কারণ"), "text", placeholder="Vaccination / check-up"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_DOCTOR,
    catalog_label=L("Vet", "ভেট"),
    catalog_label_plural=L("Vets", "ভেট"),
    catalog_fields=tuple(replace(spec, **_RELABEL.get(spec.key, {})) for spec in CLINIC_SPEC["catalog_fields"]),
    config_fields=(
        *(spec for spec in CLINIC_SPEC["config_fields"] if spec.key != "health_line"),
        FieldSpec(
            "emergency_vet",
            L("Emergency vet (optional)", "জরুরি পশু হাসপাতাল (ঐচ্ছিক)"),
            placeholder="Northside Animal ER on 5th Avenue",
            help=L("Where callers are sent in an animal emergency; empty = the nearest emergency vet.", "জরুরি অবস্থায় কলারকে যেখানে পাঠানো হবে।"),
        ),
    ),
    config_defaults={"booking_horizon_days": 21, "lead_minutes": 60},
    status_labels=dict(CLINIC_SPEC["status_labels"]),
    outbound_label=L("Reminder call", "রিমাইন্ডার কল"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["SPECIES_OPTIONS", "VET_SPEC", "summarize"]
