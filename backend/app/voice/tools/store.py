"""Where a call's results go: the store protocol, the in-memory store, the tool result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from app.flows.base import CommitAction, CommitResult
from app.flows.scheduling import slot_key

logger = structlog.get_logger(__name__)


@dataclass
class ToolResult:
    #: JSON the model reads back as the tool message.
    payload: dict[str, Any]
    #: A line the agent speaks verbatim right after the tool (bypasses the model).
    say: str = ""
    #: Hang up once ``say`` has played.
    hang_up: bool = False
    #: Dial this number once ``say`` has played (transfer).
    transfer_to: str = ""
    #: Do not call the model again in this turn.
    stop: bool = False
    #: Outcome committed by this call, if any.
    outcome: str = ""


class CallStore(Protocol):
    async def set_outcome(
        self, *, outcome: str, status: str, final_node: str, flow_data: dict[str, Any], note: str, language: str
    ) -> None: ...

    async def commit(self, action: CommitAction, *, final_node: str, flow_data: dict[str, Any], language: str) -> CommitResult: ...

    async def save_transcript(self, transcript: str, *, language: str, final_node: str) -> None: ...

    async def save_usage(self, **counters: Any) -> None:
        """Counters plus optional ``llm_stats`` / ``stt_usage`` / ``tts_usage`` for the finance engine."""
        ...


class NullCallStore:
    """Keeps every write in memory (tests, the text simulator, dry runs).

    ``taken`` is a set of :func:`slot_key` strings that already have a booking —
    a commit into one of them fails with ``slot_taken`` (the race the database
    lock guards against in production).
    """

    def __init__(self, *, taken: set[str] | None = None) -> None:
        self.outcomes: list[dict[str, Any]] = []
        self.commits: list[dict[str, Any]] = []
        self.transcripts: list[dict[str, Any]] = []
        self.usage: list[dict[str, int]] = []
        self.taken: set[str] = set(taken or ())

    async def set_outcome(self, **kwargs: Any) -> None:
        self.outcomes.append(kwargs)

    async def commit(self, action: CommitAction, **kwargs: Any) -> CommitResult:
        if action.capacity is not None:
            item_id, start, _capacity = action.capacity
            key = slot_key(item_id, start)
            if key in self.taken:
                self.taken.discard(key)
                return CommitResult(ok=False, reason="slot_taken")
        record_id = action.record_id or f"rec-{len(self.commits) + 1}"
        self.commits.append({"action": action, "record_id": record_id, **kwargs})
        self.outcomes.append({"outcome": action.outcome, "status": action.status, "note": action.note, **kwargs})
        return CommitResult(ok=True, record_id=record_id)

    async def save_transcript(self, transcript: str, **kwargs: Any) -> None:
        self.transcripts.append({"transcript": transcript, **kwargs})

    async def save_usage(self, **counters: Any) -> None:
        self.usage.append(dict(counters))


