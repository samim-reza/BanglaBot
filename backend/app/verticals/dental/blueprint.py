"""The dental practice's call pipelines — the clinic's, with dentists, dental wording,
insurance asked by default, and dental emergencies::

    greet → intent ─ book ───────▶ dentist → day → patient type* → patient name → insurance → phone
                   │                → visit mode* → payment* → approval* → read-back → book → text
                   ├ reschedule ─▶ find appointment → day → read-back → move
                   └ cancel ─────▶ find appointment → read-back → cancel
    (* off by default.)  Outbound reminder: as the clinic's.
"""

from __future__ import annotations

from typing import Any

from app.skills.library.emergency import EmergencySkill
from app.skills.library.intake import IntakeField
from app.skills.library.lines import L, line
from app.verticals.clinic.blueprint import inbound_blueprint, inbound_skills, outbound_blueprint
from app.verticals.clinic.skills import ClinicConfirmSkill, DoctorSkill
from app.verticals.dental.flow import DentalFlow

RED_FLAGS = (
    "severe facial or jaw swelling", "swelling that makes breathing or swallowing hard", "bleeding that won't stop",
    "a knocked-out tooth", "an injury to the face or jaw",
)

EMERGENCY_LINES = (
    line(
        "emergency",
        "This needs urgent care. Please call {emergency} or go to the nearest emergency room now. If a tooth was knocked out, keep it in milk and bring it with you.",
        label="Emergency line",
        variables=("emergency",),
        required=("emergency",),
    ),
)

DENTAL_FIELDS = (
    IntakeField("patient_name", L("Patient name"), L("May I have the patient's name?"), required=True, long_answer=True, hint="May differ from the caller."),
    IntakeField("insurance", L("Dental insurance"), L("Do you have dental insurance? If so, which provider?"), hint="The provider's name, or 'none'."),
    IntakeField("age", L("Age"), L("How old is the patient?"), type="number", on=False),
    IntakeField("dob", L("Date of birth"), L("What is the patient's date of birth?"), type="date", on=False),
    IntakeField("email", L("Email"), L("What email should we send the details to?"), type="email", on=False),
    IntakeField("reason", L("Reason for visit"), L("What is the visit for — a check-up, a cleaning, a toothache?"), ask=False, hint="A few words (cleaning, check-up, toothache, braces …), only if the caller says it."),
)

DENTIST_LINES = (
    line("doctor", "Which dentist would you like to see? We have {departments}.", label="Ask for a dentist", variables=("departments",)),
    line("choose", "We have {names} — who would you like to see?", label="Several match", variables=("names",)),
    line("unknown", "Sorry, I can't find that dentist. We have {departments}. Who would you like to see?", label="No match", variables=("departments",)),
)


def _confirm() -> ClinicConfirmSkill:
    """The clinic's read-back and closings, with the practice's own words where they differ."""
    lines = tuple(spec for spec in ClinicConfirmSkill.lines if spec.key != "knows_person") + (
        line("knows_person", "We have a dental appointment under the name {name} for this number. Do you know them?", label="Someone else answered", variables=("name",)),
    )
    return ClinicConfirmSkill(lines=lines)


def dental_skills() -> dict[str, Any]:
    skills = inbound_skills(DENTAL_FIELDS)
    for skill in (
        DoctorSkill(lines=DENTIST_LINES, label=L("Dentist"), description=L("Finds the right dentist by name, specialty or need."), goal="Find out which dentist (save the D-ref)."),
        EmergencySkill(red_flags=RED_FLAGS, lines=EMERGENCY_LINES),
        _confirm(),
    ):
        skills[skill.key] = skill
    return skills


INBOUND = inbound_blueprint("dental", dental_skills(), flow_cls=DentalFlow)
OUTBOUND = outbound_blueprint("dental", EMERGENCY_LINES, RED_FLAGS, flow_cls=DentalFlow, overrides={"confirm": _confirm()})
BLUEPRINTS = {"inbound": INBOUND, "outbound": OUTBOUND}

__all__ = ["BLUEPRINTS", "DENTAL_FIELDS", "EMERGENCY_LINES", "INBOUND", "OUTBOUND", "RED_FLAGS", "dental_skills"]
