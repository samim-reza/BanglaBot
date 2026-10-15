"""One bulk-call batch: its progress counters, state and the progress-view payload."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.datetime_utils import utcnow
from app.models import OrderStatus

ACTIVE_STATES = frozenset({"queued", "running"})


@dataclass
class BulkCallRun:
    merchant_id: str
    order_ids: list[str]
    statuses: tuple[OrderStatus, ...]
    source: str = "manual"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = "queued"  # queued | running | done | cancelled | failed
    started: int = 0
    failed: int = 0
    skipped: int = 0
    error: str = ""
    created_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    @property
    def total(self) -> int:
        return len(self.order_ids)

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES


def serialize_run(run: BulkCallRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "state": run.state,
        "source": run.source,
        "total": run.total,
        "started": run.started,
        "failed": run.failed,
        "skipped": run.skipped,
        "error": run.error,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
    }
