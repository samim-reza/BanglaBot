"""``DbCallStore``: the DB-backed ``CallStore`` the agent writes outcomes, bookings
(with a capacity re-check under an advisory lock), transcripts and usage through."""

from __future__ import annotations

import asyncio
from datetime import timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select, text

from app.core.datetime_utils import utcnow
from app.db.session import AsyncSessionLocal
from app.flows.base import OUTCOME_INQUIRY, CommitAction, CommitResult
from app.flows.context import DIRECTION_OUTBOUND
from app.models import CallLog, Order, OrderStatus

#: Statuses a scheduled slot stays taken in.
LIVE_RECORD_STATUSES = (OrderStatus.pending, OrderStatus.calling, OrderStatus.confirmed)
#: Record columns a commit may set.
RECORD_COLUMNS = (
    "kind", "customer_name", "customer_phone", "address", "items_summary", "total_amount",
    "catalog_item_id", "scheduled_at", "order_ref",
)


def _note_line(existing: str, note: str) -> str:
    stamp = utcnow().strftime("%Y-%m-%d %H:%M")
    line = f"[{stamp}] {note}"
    return f"{existing}\n{line}".strip() if existing else line


def _amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


class DbCallStore:
    """Persists what the agent learns: outcomes, bookings, transcript, usage.

    ``order_id`` is the record the call is about; an inbound call starts with
    none and binds the record its first commit creates.
    """

    def __init__(self, *, order_id: str, call_log_id: str, merchant_id: str = "", currency: str = "", source: str = "") -> None:
        self.order_id = order_id or ""
        self.call_log_id = call_log_id
        self.merchant_id = merchant_id
        self.currency = currency
        self.source = source

    async def set_outcome(self, *, outcome: str, status: str, final_node: str, flow_data: dict[str, Any], note: str, language: str) -> None:
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, self.order_id) if self.order_id else None
            log = await session.get(CallLog, self.call_log_id)
            if order is not None:
                if status:
                    order.status = OrderStatus(status)
                order.flow_data = dict(flow_data or {})
                if note:
                    order.notes = _note_line(order.notes or "", note)
                order.updated_at = utcnow()
            if log is not None and not (outcome == OUTCOME_INQUIRY and log.outcome and log.outcome != OUTCOME_INQUIRY):
                # A late "it was just an enquiry" (e.g. from a reconnected stream) never hides a real outcome.
                log.outcome = outcome
                log.final_node = final_node or log.final_node
                log.language = language or log.language
            await session.commit()
            merchant_id = order.merchant_id if order is not None else (log.merchant_id if log is not None else "")
        if self.order_id:
            from app.services import notification_service

            notification_service.after_outcome(merchant_id, self.order_id, outcome)

    @staticmethod
    async def _existing_by_idem(session: Any, merchant_id: str, action: CommitAction) -> str:
        """The record a previous attempt of this exact write created (``details.idem``), if any."""
        idem = str((action.fields.get("details") or {}).get("idem") or "")
        if not idem or action.record_id:
            return ""
        found = await session.scalar(
            select(Order.id).where(Order.merchant_id == merchant_id, Order.details["idem"].astext == idem).limit(1)
        )
        return str(found or "")

    async def commit(self, action: CommitAction, *, final_node: str, flow_data: dict[str, Any], language: str) -> CommitResult:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                log = await session.get(CallLog, self.call_log_id)
                merchant_id = self.merchant_id or (log.merchant_id if log is not None else "")
                if action.capacity is not None:
                    item_id, start, capacity = action.capacity
                    # Serialize bookings into the same resource so two calls can't
                    # both take its last free slot.
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{merchant_id}:{item_id or '*'}"}
                    )
                    # A retried write of a booking that already landed (same idempotency key)
                    # finds the first record instead of colliding with its own slot.
                    existing = await self._existing_by_idem(session, merchant_id, action)
                    if existing:
                        return CommitResult(ok=True, record_id=existing)
                    stmt = select(func.count(Order.id)).where(
                        Order.merchant_id == merchant_id,
                        Order.scheduled_at == start.astimezone(timezone.utc),
                        Order.status.in_(LIVE_RECORD_STATUSES),
                        # Food orders have a ready time but never take a bookable slot.
                        Order.kind != "order",
                    )
                    if item_id:
                        stmt = stmt.where(Order.catalog_item_id == item_id)
                    if action.record_id:
                        stmt = stmt.where(Order.id != action.record_id)
                    if int(await session.scalar(stmt) or 0) >= max(1, int(capacity)):
                        return CommitResult(ok=False, reason="slot_taken")
                if action.capacity is None:
                    existing = await self._existing_by_idem(session, merchant_id, action)
                    if existing:
                        return CommitResult(ok=True, record_id=existing)
                record_id = action.record_id or ""
                record: Order | None = await session.get(Order, record_id) if record_id else None
                if record is not None and str(record.merchant_id) != str(merchant_id):
                    record = None  # never another account's record, whatever id reached the action
                if record_id and record is None:
                    return CommitResult(ok=False, reason="not_found")
                if record is None:
                    record = Order(
                        merchant_id=merchant_id,
                        kind=str(action.fields.get("kind") or "order"),
                        source=self.source or "inbound_call",
                        customer_name=str(action.fields.get("customer_name") or "Caller")[:120],
                        customer_phone=str(action.fields.get("customer_phone") or "")[:32],
                        currency=self.currency,
                        status=OrderStatus(action.status),
                        details={},
                        flow_data={},
                    )
                    session.add(record)
                for key, value in action.fields.items():
                    if key == "details":
                        merged = dict(record.details or {})
                        merged.update({k: v for k, v in dict(value or {}).items() if v not in (None, "")})
                        record.details = merged
                    elif key == "scheduled_at" and value is not None:
                        record.scheduled_at = value.astimezone(timezone.utc)
                    elif key == "total_amount":
                        record.total_amount = _amount(value)
                    elif key in RECORD_COLUMNS and value is not None:
                        setattr(record, key, value)
                record.status = OrderStatus(action.status)
                record.flow_data = dict(flow_data or {})
                if action.note:
                    record.notes = _note_line(record.notes or "", action.note)
                record.updated_at = utcnow()
                await session.flush()
                if log is not None:
                    log.outcome = action.outcome
                    log.final_node = final_node or log.final_node
                    log.language = language or log.language
                    log.order_id = record.id
                new_id = record.id
        self.order_id = new_id
        from app.services import notification_service

        notification_service.after_outcome(merchant_id, new_id, action.outcome)
        return CommitResult(ok=True, record_id=new_id)

    async def save_transcript(self, transcript: str, *, language: str, final_node: str) -> None:
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, self.call_log_id)
            if log is None:
                return
            log.transcript = transcript
            log.language = language or log.language
            log.final_node = final_node or log.final_node
            await session.commit()

    async def save_usage(self, *, llm_stats: Any = None, stt_usage: Any = None, tts_usage: Any = None, **counters: int) -> None:
        """Usage counters onto the call log, then the call's priced cost lines (``app.finance``).

        ``llm_stats`` (``RoutedLLM.stats()``), ``stt_usage`` (STT sessions' ``usage()`` dicts) and
        ``tts_usage`` (per provider ``{"chars", "cached_chars"}``) price the call on the providers
        that actually served it; without them the counters are priced on the platform defaults."""
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, self.call_log_id)
            if log is None:
                return
            for key in ("llm_prompt_tokens", "llm_completion_tokens", "llm_cached_tokens", "tts_chars", "tts_cache_hits"):
                if key in counters:
                    # Added, not replaced: a stream that reconnected mid-call reports only its own share.
                    setattr(log, key, int(getattr(log, key) or 0) + int(counters[key] or 0))
            # The status callback has the billed duration for outbound calls;
            # inbound / test calls only have ours.
            if counters.get("duration_secs") and not log.duration_secs:
                log.duration_secs = int(counters["duration_secs"])
            # Outbound calls are settled by the carrier's status callback; everything else
            # (inbound, console tests, website / WhatsApp / Messenger / Instagram chats) ends here.
            if log.direction != DIRECTION_OUTBOUND and log.call_status == "in-progress":
                log.call_status = "completed"
            await session.commit()
        from app.finance import recorder

        # Detached and failure-proof: the call / chat never waits on (or sees) metering.
        recorder.schedule_call(self.call_log_id, dict(counters), llm_stats=llm_stats, stt_usage=stt_usage, tts_usage=tts_usage)

    async def notify_finished(self) -> None:
        """Webhook add-on: tell the business's own system how the call ended."""
        from app.services.webhook_service import send_call_finished

        asyncio.create_task(send_call_finished(self.call_log_id))
