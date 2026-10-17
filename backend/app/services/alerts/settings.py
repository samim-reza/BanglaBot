"""Owner alert settings (``merchants.alert_settings``) and which agent outcome is which
alert event (pure; no I/O).

Stored sparse; ``settings_of`` fills the defaults::

    {"email_events": ["booking", "message", "urgent"], "sms_events": [], "sms_to": ""}

Email goes to the account's email (only when the platform has SMTP); texts go to
``sms_to`` and count toward the plan's texts.
"""

from __future__ import annotations

import re
from typing import Any

EVENT_BOOKING = "booking"
EVENT_CHANGE = "change"
EVENT_MESSAGE = "message"
EVENT_URGENT = "urgent"
EVENTS = (EVENT_BOOKING, EVENT_CHANGE, EVENT_MESSAGE, EVENT_URGENT)

CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"

DEFAULT_SETTINGS: dict[str, Any] = {
    "email_events": [EVENT_BOOKING, EVENT_MESSAGE, EVENT_URGENT],
    "sms_events": [],
    "sms_to": "",
}

#: Agent outcome → alert event ("confirmed" counts only for an order; see ``event_for``).
OUTCOME_EVENT: dict[str, str] = {
    "booked": EVENT_BOOKING,
    "confirmed": EVENT_BOOKING,
    "rescheduled": EVENT_CHANGE,
    "cancelled": EVENT_CHANGE,
    "not_interested": EVENT_CHANGE,
    "lead": EVENT_MESSAGE,
    "relay": EVENT_MESSAGE,
    "emergency": EVENT_URGENT,
    "transfer": EVENT_URGENT,
    "unclear": EVENT_URGENT,
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _events(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return list(fallback)
    return [event for event in EVENTS if event in value]


def settings_of(merchant: Any) -> dict[str, Any]:
    stored = getattr(merchant, "alert_settings", None)
    stored = stored if isinstance(stored, dict) else {}
    return {
        "email_events": _events(stored.get("email_events"), DEFAULT_SETTINGS["email_events"]),
        "sms_events": _events(stored.get("sms_events"), DEFAULT_SETTINGS["sms_events"]),
        "sms_to": str(stored.get("sms_to") or "").strip()[:32],
    }


def email_to(merchant: Any) -> str:
    """The owner's email when it looks deliverable, else ""."""
    value = str(getattr(merchant, "email", "") or "").strip()
    return value if _EMAIL.match(value) else ""


def event_for(outcome: str, record_kind: str = "") -> str:
    """The alert an outcome raises ("" = none). A reminder call's "yes, I'll come" isn't news;
    an e-commerce order the customer confirmed is."""
    if outcome == "confirmed" and record_kind != "order":
        return ""
    return OUTCOME_EVENT.get(str(outcome or ""), "")


def channels_for(merchant: Any, event: str) -> list[str]:
    """Where this event goes for this account (recipients present; platform readiness is checked
    when sending)."""
    if event not in EVENTS:
        return []
    config = settings_of(merchant)
    out = []
    if event in config["email_events"] and email_to(merchant):
        out.append(CHANNEL_EMAIL)
    if event in config["sms_events"] and config["sms_to"]:
        out.append(CHANNEL_SMS)
    return out


__all__ = [
    "CHANNEL_EMAIL", "CHANNEL_SMS", "DEFAULT_SETTINGS", "EVENTS", "EVENT_BOOKING", "EVENT_CHANGE", "EVENT_MESSAGE", "EVENT_URGENT",
    "OUTCOME_EVENT", "channels_for", "email_to", "event_for", "settings_of",
]
