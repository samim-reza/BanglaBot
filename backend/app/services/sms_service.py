"""SMS confirmations and reminders — the import path the app uses; the code lives in
:mod:`app.services.sms`.

Note for tests: patch where a name is looked up — e.g. ``platform_ready`` as
``planned_kind`` sees it is ``app.services.sms.policy.platform_ready``.
"""

from app.services.sms import (
    DEFAULT_SETTINGS,
    LIVE,
    OUTCOME_KIND,
    TELNYX_STATUS,
    after_outcome,
    apply_status,
    compose,
    planned_kind,
    platform_ready,
    run_reminders,
    segments,
    send,
    send_due_reminders,
    settings_of,
)
from app.services.sms import sending as _sending

# Private helper imported from its old home (tests).
_sms_status_url = _sending._sms_status_url

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
