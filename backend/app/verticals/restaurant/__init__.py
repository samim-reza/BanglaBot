"""Restaurant engine: pickup / delivery orders from the menu, table reservations, order status, menu questions.

Runs on the skill pipeline (``blueprint.py``); the cart (``cart*.py``) is priced by
the backend from the menu (``menu.py``), never by the model.
"""

from __future__ import annotations

from app.verticals.base import Vertical
from app.verticals.pipelines import pipeline_vertical
from app.verticals.restaurant.blueprint import BLUEPRINTS
from app.verticals.restaurant.config import KIND_MENU_ITEM, KIND_ORDER, KIND_RESERVATION
from app.verticals.restaurant.fields import RESTAURANT_SPEC
from app.verticals.restaurant.flow import RestaurantFlow

RESTAURANT: Vertical = pipeline_vertical(RESTAURANT_SPEC, BLUEPRINTS)

__all__ = ["KIND_MENU_ITEM", "KIND_ORDER", "KIND_RESERVATION", "RESTAURANT", "RestaurantFlow"]
