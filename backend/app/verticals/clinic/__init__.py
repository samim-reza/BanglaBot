"""Clinic engine: doctor appointments (serials) for a chamber / clinic / diagnostic centre.

Runs on the skill pipeline (``blueprint.py``) unless ``PIPELINE_VERTICALS``
leaves it out, in which case the legacy hand-written flow (``legacy.py``) is used.
"""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.clinic import legacy
from app.verticals.clinic.blueprint import BLUEPRINTS
from app.verticals.clinic.catalog import KIND_APPOINTMENT, KIND_DOCTOR, doctor_availability, doctor_title
from app.verticals.clinic.fields import CLINIC_SPEC
from app.verticals.clinic.flow import ClinicFlow
from app.verticals.pipelines import pipeline_vertical

CLINIC: Vertical = pipeline_vertical(CLINIC_SPEC, BLUEPRINTS, legacy_flows={"inbound": legacy.INBOUND, "outbound": legacy.OUTBOUND})

__all__ = ["CLINIC", "KIND_APPOINTMENT", "KIND_DOCTOR", "ClinicFlow", "doctor_availability", "doctor_title"]
