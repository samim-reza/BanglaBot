"""Real-estate engine: a land / flat broker's phone line (buyers, renters, sellers, site visits, follow-ups).

Runs on the skill pipeline (``blueprint.py``) unless ``PIPELINE_VERTICALS``
leaves it out, in which case the legacy hand-written flow (``legacy.py``) is used.
"""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.pipelines import pipeline_vertical
from app.verticals.real_estate import legacy
from app.verticals.real_estate.blueprint import BLUEPRINTS
from app.verticals.real_estate.catalog import KIND_LEAD, KIND_PROPERTY, lead_score, visit_availability
from app.verticals.real_estate.fields import REAL_ESTATE_SPEC
from app.verticals.real_estate.flow import RealEstateFlow

REAL_ESTATE: Vertical = pipeline_vertical(REAL_ESTATE_SPEC, BLUEPRINTS, legacy_flows={"inbound": legacy.INBOUND, "outbound": legacy.OUTBOUND})

__all__ = ["KIND_LEAD", "KIND_PROPERTY", "REAL_ESTATE", "RealEstateFlow", "lead_score", "visit_availability"]
