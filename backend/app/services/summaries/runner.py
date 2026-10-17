"""Writing a finished conversation's summary onto its call log, in the background.

``schedule`` (from the call store when a call / chat ends) starts ``summarize`` in a
detached task: one short request on the account's LLM chain (the same router and
fallbacks as calls; a fast setting per model, at most ``MAX_OUTPUT_TOKENS``), the
cleaned answer saved as ``call_logs.summary`` and its tokens metered (category llm).
Never raises: a failed or unconfigured LLM just means no summary.

Owner alerts wait briefly for it (``wait_for``); every run ends by waking them,
with the summary or "".
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

import structlog

from app.services.summaries import prompt

logger = structlog.get_logger(__name__)

MAX_OUTPUT_TOKENS = 120
#: Finished runs remembered for late waiters (this process only).
MAX_REMEMBERED = 500

#: Session factory / LLM factory (tests swap in fakes).
session_factory: Any = None
llm_factory: Any = None
#: Running summaries (strong references, so they aren't garbage-collected mid-way).
_pending: set[asyncio.Task[Any]] = set()
_done: OrderedDict[str, str] = OrderedDict()
_events: OrderedDict[str, asyncio.Event] = OrderedDict()


def sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


def make_llm(merchant: Any) -> Any:
    """The account's chain, sized for a summary; None when no LLM is configured."""
    if llm_factory is not None:
        return llm_factory(merchant)
    from app.voice.providers.llm import factory

    if not factory.llm_configured(merchant):
        return None
    return factory.llm_for_call(flow_key="summary", merchant=merchant, channel="chat", max_output_tokens=MAX_OUTPUT_TOKENS)


# ------------------------------------------------------------------ waiters
def _signal(call_log_id: str, text: str) -> None:
    _done[call_log_id] = text
    _done.move_to_end(call_log_id)
    while len(_done) > MAX_REMEMBERED:
        _done.popitem(last=False)
    event = _events.pop(call_log_id, None)
    if event is not None:
        event.set()


async def wait_for(call_log_id: str, timeout: float) -> str | None:
    """The summary once this process wrote it ("" = none will come); None after ``timeout``."""
    if not call_log_id:
        return None
    if call_log_id in _done:
        return _done[call_log_id]
    event = _events.get(call_log_id)
    if event is None:
        event = _events[call_log_id] = asyncio.Event()
        while len(_events) > MAX_REMEMBERED:
            _events.popitem(last=False)
    try:
        await asyncio.wait_for(event.wait(), timeout=max(0.0, timeout))
    except asyncio.TimeoutError:
        return None
    return _done.get(call_log_id)


# ------------------------------------------------------------------ the run
async def _load(call_log_id: str) -> tuple[Any, Any, Any, str] | None:
    """(log, merchant, record, item name) of a conversation worth summarizing, else None."""
    from app.models import CallLog, CatalogItem, Merchant, Order

    async with sessions()() as session:
        log = await session.get(CallLog, call_log_id)
        if log is None or getattr(log, "summary", None) or not prompt.has_caller_turn(log.transcript):
            return None
        merchant = await session.get(Merchant, log.merchant_id)
        if merchant is None:
            return None
        record = await session.get(Order, log.order_id) if log.order_id else None
        item = await session.get(CatalogItem, record.catalog_item_id) if record is not None and record.catalog_item_id else None
        return log, merchant, record, (item.name if item is not None else "")


def messages_for(log: Any, merchant: Any, record: Any, item_name: str) -> list[dict[str, str]]:
    from app.services.sms.composer import _money, _when

    when = _when(record, merchant, "en") if record is not None else ""
    amount = ""
    if record is not None:
        amount = _money(getattr(record, "total_amount", 0), str(getattr(record, "currency", "") or getattr(merchant, "currency", "") or "USD"))
    lines = prompt.facts(
        business=str(getattr(merchant, "business_name", "") or ""), direction=str(log.direction or ""),
        caller_number=str(log.caller_number or ""), outcome=str(log.outcome or ""), record=record,
        when=when, amount=amount, item_name=item_name,
    )
    return prompt.build_messages(lines, log.transcript or "")


async def _save(call_log_id: str, text: str) -> None:
    from app.models import CallLog

    async with sessions()() as session:
        log = await session.get(CallLog, call_log_id)
        if log is None:
            return
        log.summary = text
        await session.commit()


async def summarize(call_log_id: str) -> str:
    """Generate, store and meter one conversation's summary. Returns it ("" = none). Never raises."""
    text = ""
    try:
        loaded = await _load(call_log_id)
        if loaded is None:
            return ""
        log, merchant, record, item_name = loaded
        llm = make_llm(merchant)
        if llm is None:
            return ""
        try:
            reply = await llm.complete(messages_for(log, merchant, record, item_name))
        finally:
            await _meter(llm, merchant_id=str(log.merchant_id), call_log_id=call_log_id)
        text = prompt.clean(reply.content)
        if text:
            await _save(call_log_id, text)
            await logger.ainfo("call_summary_saved", call_log_id=call_log_id, chars=len(text))
        return text
    except Exception as exc:  # noqa: BLE001 — a summary is a nice-to-have, never a failure
        await logger.awarning("call_summary_failed", call_log_id=call_log_id, error=str(exc)[:200], error_type=type(exc).__name__)
        return ""
    finally:
        # Waiting alerts get what was written (even when saving it failed).
        _signal(call_log_id, text)


async def _meter(llm: Any, *, merchant_id: str, call_log_id: str) -> None:
    stats = getattr(llm, "stats", None)
    usage = stats() if callable(stats) else None
    if not usage or not (usage.get("prompt_tokens") or usage.get("completion_tokens")):
        return
    from app.finance import recorder

    await recorder.record_llm_extra(merchant_id, call_log_id, usage, purpose="summary")


def schedule(call_log_id: str) -> None:
    """Summarize a finished call / chat in the background (no running loop: skipped). Never raises."""
    if not call_log_id:
        return
    try:
        task = asyncio.get_running_loop().create_task(summarize(call_log_id))
    except RuntimeError:
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)


__all__ = ["MAX_OUTPUT_TOKENS", "make_llm", "messages_for", "schedule", "summarize", "wait_for"]
