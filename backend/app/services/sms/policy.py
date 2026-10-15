"""Who gets a text: the account's SMS settings, platform readiness, and which text an
agent outcome triggers (pure; no I/O)."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

DEFAULT_SETTINGS: dict[str, Any] = {"enabled": False, "on_booking": True, "on_change": True, "reminder_hours": 24}
#: Agent outcome → the text it triggers.
OUTCOME_KIND = {"booked": "confirmation", "rescheduled": "change", "cancelled": "cancellation", "lead": "lead", "confirmed": "confirmation"}


def settings_of(merchant: Any) -> dict[str, Any]:
    stored = getattr(merchant, "sms_settings", None)
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(stored, dict):
        merged.update({key: value for key, value in stored.items() if key in DEFAULT_SETTINGS and value is not None})
    return merged


def platform_ready() -> bool:
    settings = get_settings()
    return bool(
        settings.sms_enabled
        and settings.telnyx_api_key
        and (settings.telnyx_sms_from or settings.telnyx_from_number)
    )


def planned_kind(merchant: Any, outcome: str, *, record_kind: str = "", phone: str = "") -> str | None:
    """Which text an outcome sends to this account's customer, or None (pure; no I/O)."""
    config = settings_of(merchant)
    if not config["enabled"] or not phone or not platform_ready():
        return None
    kind = OUTCOME_KIND.get(outcome)
    if kind is None:
        return None
    if outcome == "confirmed" and record_kind != "order":
        # A reminder call's "yes, I'll come" needs no extra text; an e-commerce confirmation does.
        return None
    if kind in ("confirmation", "lead") and not config["on_booking"]:
        return None
    if kind in ("change", "cancellation") and not config["on_change"]:
        return None
    return kind
