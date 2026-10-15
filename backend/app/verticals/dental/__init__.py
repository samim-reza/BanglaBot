"""Dental engine: a dental practice's appointments on the clinic engine (dentists, insurance, dental emergencies)."""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.dental.blueprint import BLUEPRINTS
from app.verticals.dental.fields import DENTAL_SPEC
from app.verticals.dental.flow import DentalFlow
from app.verticals.pipelines import pipeline_vertical

DENTAL: Vertical = pipeline_vertical(DENTAL_SPEC, BLUEPRINTS)

__all__ = ["DENTAL", "DentalFlow"]
