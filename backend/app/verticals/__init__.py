"""Business engines plugged into the main call engine.

Each vertical (see :class:`app.verticals.base.Vertical`) brings its own
conversation flows, record / catalog vocabulary and settings. An account's
vertical is chosen by the admin when the account is created and never changes.

    ecommerce    — order confirmation calls (outbound) + reception (inbound)
    clinic       — doctor appointments / serials (inbound) + reminders (outbound)
    real_estate  — buyer / renter / seller leads + site visits (inbound) + follow-ups (outbound)
    home_service — technician bookings (inbound) + visit confirmations (outbound)
"""

from __future__ import annotations

from typing import Any

from app.flows.base import Flow
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.verticals.base import Vertical
from app.verticals.clinic import CLINIC
from app.verticals.ecommerce import ECOMMERCE
from app.verticals.home_service import HOME_SERVICE
from app.verticals.real_estate import REAL_ESTATE

VERTICALS: dict[str, Vertical] = {vertical.key: vertical for vertical in (ECOMMERCE, CLINIC, REAL_ESTATE, HOME_SERVICE)}
DEFAULT_VERTICAL = ECOMMERCE.key


def get_vertical(key: Any) -> Vertical:
    return VERTICALS.get(str(key or "").strip().lower(), VERTICALS[DEFAULT_VERTICAL])


def is_vertical(key: Any) -> bool:
    return str(key or "").strip().lower() in VERTICALS


def vertical_for(merchant: Any) -> Vertical:
    return get_vertical(getattr(merchant, "vertical", None))


def flow_for(merchant: Any, direction: str) -> Flow:
    """The flow a call of ``direction`` runs for this merchant (outbound falls back to inbound and vice versa)."""
    vertical = vertical_for(merchant)
    flow = vertical.flow(direction)
    if flow is None:
        other = DIRECTION_INBOUND if direction == DIRECTION_OUTBOUND else DIRECTION_OUTBOUND
        flow = vertical.flow(other)
    assert flow is not None, f"vertical {vertical.key} has no flows"
    return flow


__all__ = ["DEFAULT_VERTICAL", "VERTICALS", "Vertical", "flow_for", "get_vertical", "is_vertical", "vertical_for"]
