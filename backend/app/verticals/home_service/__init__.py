"""Home-service engine: plumber, electrician, AC servicing, cleaning, pest control…

Runs on the skill pipeline (``blueprint.py``) unless ``PIPELINE_VERTICALS``
leaves it out, in which case the legacy hand-written flow (``legacy.py``) is used.
"""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.home_service import legacy
from app.verticals.home_service.blueprint import BLUEPRINTS
from app.verticals.home_service.catalog import KIND_BOOKING, KIND_SERVICE, service_availability
from app.verticals.home_service.fields import HOME_SERVICE_SPEC
from app.verticals.home_service.flow import HomeServiceFlow
from app.verticals.pipelines import pipeline_vertical

HOME_SERVICE: Vertical = pipeline_vertical(HOME_SERVICE_SPEC, BLUEPRINTS, legacy_flows={"inbound": legacy.INBOUND, "outbound": legacy.OUTBOUND})

__all__ = ["HOME_SERVICE", "KIND_BOOKING", "KIND_SERVICE", "HomeServiceFlow", "service_availability"]
