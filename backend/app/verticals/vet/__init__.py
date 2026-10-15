"""Vet engine: a veterinary clinic's appointments on the clinic engine (owner + pet, animal emergencies)."""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.pipelines import pipeline_vertical
from app.verticals.vet.blueprint import BLUEPRINTS
from app.verticals.vet.fields import VET_SPEC
from app.verticals.vet.flow import VetFlow

VET: Vertical = pipeline_vertical(VET_SPEC, BLUEPRINTS)

__all__ = ["VET", "VetFlow"]
