"""Owner alerts: an email and / or a text to the owner when the agent books, takes a
message, or handles something urgent.

``settings`` (stored choices, outcome → event; pure), ``compose`` (wording; pure),
``dispatch`` (once per outcome, in the background; the test alert).
"""

from app.services.alerts.dispatch import deliver, schedule, send_test
from app.services.alerts.settings import DEFAULT_SETTINGS, EVENTS, channels_for, email_to, event_for, settings_of

__all__ = ["DEFAULT_SETTINGS", "EVENTS", "channels_for", "deliver", "email_to", "event_for", "schedule", "send_test", "settings_of"]
