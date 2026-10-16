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
    label=L("Doctor appointments"),
    description=L(
        "Answers the clinic's phone: books doctor appointments, moves or cancels appointments, answers questions about doctors, days and fees, and calls patients with reminders.",
    ),
    record_kind=KIND_APPOINTMENT,
    record_label=L("Appointment"),
    record_label_plural=L("Appointments"),
    record_fields=(
        FieldSpec("customer_name", L("Patient name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Doctor"), "catalog", required=True, list_column=True),
        FieldSpec("scheduled_at", L("Date & time"), "datetime", required=True, list_column=True),
        FieldSpec("serial", L("Queue / serial no."), "number"),
        FieldSpec("reason", L("Reason"), "text"),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    catalog_kind=KIND_DOCTOR,
    catalog_label=L("Doctor"),
    catalog_label_plural=L("Doctors"),
    catalog_fields=(
        FieldSpec("name", L("Doctor's name"), required=True, placeholder="Dr. Abdul Karim"),
        FieldSpec("specialty", L("Department / specialty"), required=True, placeholder="Medicine / Pediatrics"),
        FieldSpec("degrees", L("Degrees"), placeholder="MBBS, FCPS (Medicine)"),
        FieldSpec("days", L("Chamber days"), "days", required=True),
        FieldSpec("start_time", L("Starts at"), "time", required=True, default="17:00"),
        FieldSpec("end_time", L("Ends at"), "time", required=True, default="21:00"),
        FieldSpec(
            "slot_minutes",
            L("Minutes per patient"),
            "number",
            default=15,
            help=L("Serial n arrives at start + (n − 1) × this."),
        ),
        FieldSpec("max_patients", L("Max patients per day"), "number", default=0, help=L("0 = no limit")),
        FieldSpec("fee", L("Consultation fee"), "money"),
        FieldSpec("online", L("Offers online (video) visits"), "bool"),
        FieldSpec("notes", L("Notes for the agent"), "textarea", placeholder="Room 304. Reports shown free within 7 days."),
        FieldSpec(
            "calendar_ics",
            L("Busy calendar (iCal link)"),
            placeholder="https://calendar.google.com/calendar/ical/…/basic.ics",
            help=L(
                "Optional. The doctor's private iCal address (Google Calendar → Settings → Secret address in iCal format). Busy times are never offered.",
            ),
        ),
    ),
    config_fields=(
        FieldSpec("booking_horizon_days", L("Book how many days ahead"), "number", default=14),
        FieldSpec("lead_minutes", L("Earliest booking (minutes from now)"), "number", default=30),
        FieldSpec(
            "queue_numbers",
            L("Tell patients a queue (serial) number"),
            "bool",
            help=L("Common in South Asian chambers. Unset = on for BD/IN/PK accounts."),
        ),
        FieldSpec(
            "health_line",
            L("Health advice line (optional)"),
            placeholder="111 (NHS)",
            help=L("Suggested for medical questions; empty = the region's line, if any."),
        ),
    ),
    config_defaults={"booking_horizon_days": 14, "lead_minutes": 30},
    status_labels={
        "pending": L("Scheduled"),
        "confirmed": L("Confirmed"),
        "cancelled": L("Cancelled"),
        "needs_review": L("Needs review"),
    },
    outbound_label=L("Reminder call"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["CLINIC_SPEC", "summarize"]
