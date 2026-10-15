"""Salon & spa engine: services booked with a stylist / therapist (or anyone free), duration-aware.

Two catalog kinds — services and staff (``Vertical.catalog_kinds``). Inbound only;
runs on the skill pipeline (no legacy flow).
"""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.pipelines import pipeline_vertical
from app.verticals.salon.blueprint import BLUEPRINTS
from app.verticals.salon.catalog import KIND_BOOKING, KIND_SERVICE, KIND_STAFF
from app.verticals.salon.fields import SALON_SPEC
from app.verticals.salon.flow import SalonFlow

SALON: Vertical = pipeline_vertical(SALON_SPEC, BLUEPRINTS)

__all__ = ["KIND_BOOKING", "KIND_SERVICE", "KIND_STAFF", "SALON", "SalonFlow"]
