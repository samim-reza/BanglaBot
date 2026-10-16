"""Every scenario, built against the pinned business-local "now"."""

from __future__ import annotations

from datetime import datetime

from scripts.scenarios.cases import booking, outbound, restaurant
from scripts.scenarios.model import Scenario


def all_scenarios(now: datetime) -> list[Scenario]:
    return booking.scenarios(now) + restaurant.scenarios(now) + outbound.scenarios(now)
