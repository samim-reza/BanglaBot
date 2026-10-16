"""After a commit, inbound calls stay open: "anything else?" — change or cancel what was just
written, another request, or a polite goodbye.

The record just written joins the caller's records (so the reschedule / cancel branches find it),
who the caller is is kept, and new details for that record with no new request amend it in place.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.flows import hearing
from app.flows.base import OUTCOME_CANCELLED, CommitAction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.scheduling import slot_key

#: Set after a commit when the call stays open for "anything else?" (never persisted: "_" prefix).
AFTER = "_after"
#: The request just written (its slots + record id), so "move it to Thursday" can amend it.
LAST = "_last"
#: Set while amending that record: the next commit updates it instead of writing a new one.
AMEND = "_amend"
#: Who the caller is — kept when the call reopens for another request.
PERSON_SLOTS = ("customer_name", "patient_name", "caller_name", "owner_name", "phone", "email")
#: A person's name (a different one means a new request for someone else).
NAME_SLOTS = ("customer_name", "patient_name", "caller_name", "owner_name")
#: Requests one call may complete before the agent wraps up.
MAX_FOLLOW_UPS = 3
#: The end_call tool (named here to keep the pipeline free of the voice package).
END_CALL_TOOL = "end_call"


class RecordView(SimpleNamespace):
    """A record written earlier in this call, shaped like an ``Order`` for skills that look records up."""

    def __getattr__(self, name: str) -> Any:
        return None


class PipelineFollowUpMixin:
    """Mixed into :class:`~app.pipeline.flow.PipelineFlow`."""

    @staticmethod
    def _amend_last(fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext | None = None) -> None:
        """After "anything else?": new details for the request just written (no new intent) amend that record."""
        last = slots.get(LAST)
        if not slots.get(AFTER) or not last or fields.get("intent") or slots.get("intent"):
            return  # a new request has started: nothing amends the old one any more
        before = last["slots"]
        someone_else = any(
            fields.get(key) and before.get(key) and " ".join(str(fields[key]).split()).casefold() != " ".join(str(before[key]).split()).casefold()
            for key in NAME_SLOTS
        )
        if someone_else:
            # "…and one for my husband Mark": a new request of the same kind, not a change to the first.
            if before.get("intent"):
                fields["intent"] = before["intent"]
            return
        changes = {key for key in fields if key not in (*PERSON_SLOTS, "note", "reply", "confirmed")}
        if not changes or not changes & set(before):
            return
        person = {key: slots[key] for key in PERSON_SLOTS if slots.get(key) not in (None, "")}
        slots.clear()
        slots.update(last["slots"])
        slots.update(person)
        slots[AMEND] = last["record_id"]
        if ctx is not None:
            # The record being moved frees its own slot ("move it to 2" when it is at 2 is not "2 is taken").
            for key in last.get("held") or ():
                ctx.booked[key] = max(0, ctx.booked.get(key, 0) - 1)

    # ---- "anything else?" after a commit ---------------------------------------------------------
    def follows_up(self, action: CommitAction, done_so_far: int) -> bool:
        """Keep an inbound call open after this write so the caller can change it or ask for more."""
        return (
            self.direction == DIRECTION_INBOUND
            and any(b.key == "intent" for b in self.cp.prelude)
            and done_so_far < MAX_FOLLOW_UPS
        )

    def reopen(self, runtime: Any, action: CommitAction, record_id: str) -> None:
        """Start over at the router: the record just written is the caller's (to change or cancel), who they are is kept."""
        ctx = runtime.ctx
        rid = str(record_id or action.record_id or "")
        record = RecordView(**{**action.fields, "id": rid, "status": action.status})
        cancelled = action.outcome == OUTCOME_CANCELLED or str(getattr(action.status, "value", action.status)) == "cancelled"
        ctx.caller_records = [r for r in ctx.caller_records if str(getattr(r, "id", "")) != rid] + ([] if cancelled else [record])
        held: list[str] = []
        if action.capacity is not None and not cancelled:
            item_id, start, _capacity = action.capacity
            for key in {slot_key(item_id, start), slot_key(None, start)}:
                ctx.booked[key] = ctx.booked.get(key, 0) + 1
                held.append(key)
        kept = {key: runtime.slots[key] for key in PERSON_SLOTS if runtime.slots.get(key) not in (None, "")}
        snapshot = {
            key: value for key, value in runtime.slots.items()
            if not key.startswith("_") and key not in ("confirmed", "decision") and value not in (None, "")
        }
        slots = self.initial_slots(ctx)
        slots.update(kept)
        slots.pop("intent", None)
        slots[AFTER] = True
        if not cancelled and rid:
            slots[LAST] = {"slots": snapshot, "record_id": rid, "held": held}
        runtime.slots = slots
        runtime.outcome = ""
        runtime.reasks = 0
        runtime.advance()

    def fast_terminal(self, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> str | None:
        """'No thanks, that's all' to "anything else?" ends the call without the model."""
        if slots.get(AFTER) and stage == "intent" and hearing.is_done(text):
            return END_CALL_TOOL
        return None


__all__ = ["AFTER", "AMEND", "LAST", "MAX_FOLLOW_UPS", "PERSON_SLOTS", "PipelineFollowUpMixin", "RecordView"]
