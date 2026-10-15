"""Call lifecycle: place outbound calls, answer inbound ones, open test calls,
apply Telnyx callbacks, settle records whose callback never arrived — and the
DB-backed ``CallStore`` the agent writes outcomes, bookings and transcripts through.

Modules: ``policy`` (statuses, time limit, telephony / plan gates), ``outbound``,
``inbound`` (routing, answer, recording, webhook config), ``console`` (test calls),
``callbacks`` (status / AMD / recording callbacks, stale-call reconcile), ``control``
(transfer, hangup, lookups, recordings), ``store`` (``DbCallStore``), ``warmup``.

``app.services.call_service`` re-exports all of it (the import path callers use).
"""

from app.services.calls.callbacks import (
    MACHINE_ANSWERS,
    apply_amd_callback,
    apply_log_recording_callback,
    apply_recording_callback,
    apply_status_callback,
    is_machine_answer,
    reconcile_stale_calls,
)
from app.services.calls.console import open_test_call
from app.services.calls.control import complete_call, fetch_call_details, fetch_recording, redirect_call_to_human
from app.services.calls.inbound import (
    answer_inbound_call,
    configure_inbound_webhook,
    find_inbound_merchant,
    remember_call_sid,
    start_call_recording,
)
from app.services.calls.outbound import start_outbound_call
from app.services.calls.policy import (
    FAILED_CALL_STATUSES,
    LIVE_CALL_STATUSES,
    STALE_CALL_GRACE_SECONDS,
    call_time_limit,
    require_telephony,
    require_voice,
)
from app.services.calls.store import LIVE_RECORD_STATUSES, RECORD_COLUMNS, DbCallStore

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
    "redirect_call_to_human",
    "remember_call_sid",
    "require_telephony",
    "require_voice",
    "start_call_recording",
    "start_outbound_call",
]
