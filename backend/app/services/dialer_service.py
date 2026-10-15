"""Bulk dialer — the import path the app uses; the code lives in :mod:`app.services.dialer`.

Note for tests: the batch loop's seams (``_dial_one``, ``_live_calls``,
``SLOT_POLL_SECONDS``) and the ``_runs`` registry live in ``app.services.dialer.batch``.
"""

from app.services.dialer import (
    ACTIVE_STATES,
    DEFAULT_BATCH_STATUSES,
    SCHEDULER_INTERVAL_SECONDS,
    SLOT_POLL_SECONDS,
    BatchAborted,
    BulkCallRun,
    cancel_batch,
    clear_schedule,
    count_eligible,
    current_run,
    eligible_order_ids,
    eligible_statement,
    fire_due_schedules,
    next_daily,
    preflight,
    run_scheduler,
    serialize_run,
    set_schedule,
    start_batch,
    status_payload,
)

__all__ = [
    "ACTIVE_STATES",
    "DEFAULT_BATCH_STATUSES",
    "SCHEDULER_INTERVAL_SECONDS",
    "SLOT_POLL_SECONDS",
    "BatchAborted",
    "BulkCallRun",
    "cancel_batch",
    "clear_schedule",
    "count_eligible",
    "current_run",
    "eligible_order_ids",
    "eligible_statement",
    "fire_due_schedules",
    "next_daily",
    "preflight",
    "run_scheduler",
    "serialize_run",
    "set_schedule",
    "start_batch",
    "status_payload",
]
