"""The owner dashboard's summary of what the agent did (``GET /api/dashboard/summary``)."""

from app.services.dashboard.hours import DEFAULT_HOURS, working_hours
from app.services.dashboard.service import range_bounds, summary

__all__ = ["DEFAULT_HOURS", "range_bounds", "summary", "working_hours"]
