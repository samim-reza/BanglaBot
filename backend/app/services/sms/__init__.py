"""SMS confirmations and reminders over Telnyx Messaging.

When the agent books, moves or cancels something (or a COD order is confirmed),
the customer gets a short text with the details; appointments, visits and
viewings also get a reminder ``reminder_hours`` before they start. Every text is
logged in ``messages`` with its delivery status (Telnyx receipts update it).

Account settings live in ``merchants.sms_settings``::

    {"enabled": true, "on_booking": true, "on_change": true, "reminder_hours": 24}

Modules: ``policy`` (settings, platform readiness, ``planned_kind``), ``composer``
(texts + segments), ``sending`` (send + log, receipts, ``after_outcome``),
``reminders`` (due reminders + lifespan loop). ``app.services.sms_service``
re-exports all of it (the import path callers use).
"""

from app.services.sms.composer import compose, segments
from app.services.sms.policy import DEFAULT_SETTINGS, OUTCOME_KIND, planned_kind, platform_ready, settings_of
from app.services.sms.reminders import LIVE, run_reminders, send_due_reminders
from app.services.sms.sending import TELNYX_STATUS, after_outcome, apply_status, send

__all__ = [
    "DEFAULT_SETTINGS",
    "LIVE",
    "OUTCOME_KIND",
    "TELNYX_STATUS",
    "after_outcome",
    "apply_status",
    "compose",
    "planned_kind",
    "platform_ready",
    "run_reminders",
    "segments",
    "send",
    "send_due_reminders",
    "settings_of",
]
