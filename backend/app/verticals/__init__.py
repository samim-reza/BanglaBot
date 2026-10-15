"""Business engines plugged into the main call engine.

Each vertical (see :class:`app.verticals.base.Vertical`) brings its own
conversation flows, record / catalog vocabulary and settings. An account's
vertical is chosen when the account is created and never changes.

    ecommerce    — order confirmation calls (outbound) + reception (inbound)
    clinic       — doctor appointments / serials (inbound) + reminders (outbound)
    dental       — dental appointments with insurance on the clinic engine (inbound) + reminders (outbound)
    vet          — pet appointments (owner + pet) on the clinic engine (inbound) + reminders (outbound)
    salon        — salon & spa bookings: service + stylist, duration-aware (inbound)
    real_estate  — buyer / renter / seller leads + site visits (inbound) + follow-ups (outbound)
    home_service — technician bookings, moves, cancellations (inbound) + visit confirmations (outbound)
    restaurant   — pickup / delivery orders from the menu, table reservations, order status (inbound)
    custom       — build your own: bookings, an owner-built intake, messages (inbound)

The registry loads lazily: helper modules (``app.verticals.common``, ``forms``,
``reception`` …) are imported by the skill library, and importing every vertical
up front would loop back into the pipeline. To add a vertical, append its
``(module, attribute)`` to ``_REGISTRY``.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

from app.flows.base import Flow
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.verticals.base import Vertical

#: (module, attribute) of every vertical, in the order the portal lists them.
_REGISTRY: tuple[tuple[str, str], ...] = (
    ("app.verticals.ecommerce", "ECOMMERCE"),
    ("app.verticals.clinic", "CLINIC"),
    ("app.verticals.dental", "DENTAL"),
    ("app.verticals.vet", "VET"),
    ("app.verticals.salon", "SALON"),
    ("app.verticals.real_estate", "REAL_ESTATE"),
    ("app.verticals.home_service", "HOME_SERVICE"),
    ("app.verticals.restaurant", "RESTAURANT"),
    ("app.verticals.custom", "CUSTOM"),
)
DEFAULT_VERTICAL = "ecommerce"


@lru_cache(maxsize=1)
def _verticals() -> dict[str, Vertical]:
    loaded: dict[str, Vertical] = {}
    for module, attribute in _REGISTRY:
        vertical = getattr(importlib.import_module(module), attribute)
        loaded[vertical.key] = vertical
    return loaded


def __getattr__(name: str) -> Any:  # PEP 562: ``from app.verticals import VERTICALS`` stays valid
    if name == "VERTICALS":
        return _verticals()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_vertical(key: Any) -> Vertical:
    verticals = _verticals()
    return verticals.get(str(key or "").strip().lower(), verticals[DEFAULT_VERTICAL])


def is_vertical(key: Any) -> bool:
    return str(key or "").strip().lower() in _verticals()


def vertical_for(merchant: Any) -> Vertical:
    return get_vertical(getattr(merchant, "vertical", None))


def flow_for(merchant: Any, direction: str) -> Flow:
    """The flow a call of ``direction`` runs for this merchant (outbound falls back to inbound and vice versa).

    Pipeline verticals compile the account's own call-flow settings (cached by hash)."""
    from app.verticals.pipelines import compiled_flow

    vertical = vertical_for(merchant)
    compiled = compiled_flow(vertical, merchant, direction)
    if compiled is not None:
        return compiled
    flow = vertical.flow(direction)
    if flow is None:
        other = DIRECTION_INBOUND if direction == DIRECTION_OUTBOUND else DIRECTION_OUTBOUND
        flow = vertical.flow(other)
    assert flow is not None, f"vertical {vertical.key} has no flows"
    return flow


__all__ = ["DEFAULT_VERTICAL", "VERTICALS", "Vertical", "flow_for", "get_vertical", "is_vertical", "vertical_for"]
