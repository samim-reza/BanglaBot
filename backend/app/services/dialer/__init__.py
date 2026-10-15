"""Bulk dialer: "Call all" batches and the scheduled auto-call.

A batch dials every order that still needs a confirmation call, a few at a
time (``bulk_call_max_concurrent``), starting the next one as soon as a live
call settles. Batches are in-process state (one per merchant, the latest one
is kept for the progress view); the schedule itself lives on the merchant row
so it survives restarts and fires from ``run_scheduler`` in the app lifespan.

Modules: ``run`` (``BulkCallRun`` + its payload), ``queries`` (who gets dialed),
``batch`` (start / cancel / dial loop + the per-account registry), ``schedule``
(auto-call). ``app.services.dialer_service`` re-exports all of it.
"""

from app.services.dialer.batch import (
    SLOT_POLL_SECONDS,
    BatchAborted,
    cancel_batch,
    current_run,
    preflight,
    start_batch,
    status_payload,
)
from app.services.dialer.queries import DEFAULT_BATCH_STATUSES, count_eligible, eligible_order_ids, eligible_statement
from app.services.dialer.run import ACTIVE_STATES, BulkCallRun, serialize_run
from app.services.dialer.schedule import (
    SCHEDULER_INTERVAL_SECONDS,
    clear_schedule,
    fire_due_schedules,
    next_daily,
    run_scheduler,
    set_schedule,
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
