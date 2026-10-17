"""Call lifecycle — the import path the app uses; the code lives in :mod:`app.services.calls`.

Callers (and tests) reach these through the module (``call_service.start_outbound_call``,
``from app.services.call_service import DbCallStore``), so patching an attribute here
redirects every caller that looks it up at call time.
"""

from app.services.calls import (
    FAILED_CALL_STATUSES,
    LIVE_CALL_STATUSES,
    LIVE_RECORD_STATUSES,
    MACHINE_ANSWERS,
    RECORD_COLUMNS,
    STALE_CALL_GRACE_SECONDS,
    DbCallStore,
    answer_inbound_call,
    apply_amd_callback,
    apply_log_recording_callback,
    apply_recording_callback,
    apply_status_callback,
    call_time_limit,
    complete_call,
    configure_inbound_webhook,
    fetch_call_details,
    fetch_recording,
    find_inbound_merchant,
    is_machine_answer,
    open_test_call,
    reconcile_stale_calls,
    redirect_call_to_emergency,
    redirect_call_to_human,
    remember_call_sid,
    require_telephony,
    require_voice,
    start_call_recording,
    start_outbound_call,
)
from app.services.calls import callbacks as _callbacks

# Private helper imported from its old home (tests).
_settle_from_call_status = _callbacks._settle_from_call_status

__all__ = [
    "FAILED_CALL_STATUSES",
    "LIVE_CALL_STATUSES",
    "LIVE_RECORD_STATUSES",
    "MACHINE_ANSWERS",
    "RECORD_COLUMNS",
    "STALE_CALL_GRACE_SECONDS",
    "DbCallStore",
    "answer_inbound_call",
    "apply_amd_callback",
    "apply_log_recording_callback",
    "apply_recording_callback",
    "apply_status_callback",
    "call_time_limit",
    "complete_call",
    "configure_inbound_webhook",
    "fetch_call_details",
    "fetch_recording",
    "find_inbound_merchant",
    "is_machine_answer",
    "open_test_call",
    "reconcile_stale_calls",
    "redirect_call_to_emergency",
    "redirect_call_to_human",
    "remember_call_sid",
    "require_telephony",
    "require_voice",
    "start_call_recording",
    "start_outbound_call",
]
