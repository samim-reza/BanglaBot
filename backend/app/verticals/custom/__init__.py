"""Custom engine (build your own): bookings over generic resources, an owner-built intake, messages.

The owner adds their own questions (intake custom fields), switches payment /
approval / booking on or off, and lists what can be booked as catalog resources.
"""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.custom.blueprint import BLUEPRINTS
from app.verticals.custom.catalog import KIND_BOOKING, KIND_RESOURCE
from app.verticals.custom.fields import CUSTOM_SPEC
from app.verticals.custom.flow import CustomFlow
from app.verticals.pipelines import pipeline_vertical

CUSTOM: Vertical = pipeline_vertical(CUSTOM_SPEC, BLUEPRINTS)

__all__ = ["CUSTOM", "KIND_BOOKING", "KIND_RESOURCE", "CustomFlow"]
