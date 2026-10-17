"""Sending owner alerts: once per outcome, fire-and-forget, never raising.

``schedule`` (from ``notification_service.after_outcome`` when the agent writes an outcome)
starts ``deliver`` in a detached task. It finds the event and the channels the owner chose,
claims a dedupe key (record or call + event + call: an outcome written twice in one call
alerts once), waits briefly for the call's AI summary (urgent: shorter) and sends the
email (SMTP, in a thread) and / or the text (logged in ``messages``, counted toward the
plan, STOP-aware like every text).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.ratelimit import backends
from app.services.alerts import compose
from app.services.alerts.settings import CHANNEL_EMAIL, CHANNEL_SMS, EVENT_URGENT, OUTCOME_EVENT, channels_for, email_to, event_for, settings_of

logger = structlog.get_logger(__name__)

#: How long an alert waits for the call's summary (the call may still be going on).
SUMMARY_WAIT_SECONDS = 60.0
URGENT_SUMMARY_WAIT_SECONDS = 15.0
DEDUPE_SECONDS = 24 * 3600

#: Session factory (tests swap in a fake).
session_factory: Any = None
_pending: set[asyncio.Task[Any]] = set()


def sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


def smtp_ready() -> bool:
    from app.core.email import smtp_configured

    return smtp_configured()


def sms_ready() -> bool:
    from app.services.sms.policy import platform_ready

    return platform_ready()


async def _load(merchant_id: str, record_id: str, call_log_id: str) -> tuple[Any, Any, Any, str]:
    from app.models import CallLog, CatalogItem, Merchant, Order

    async with sessions()() as session:
        merchant = await session.get(Merchant, merchant_id) if merchant_id else None
        record = await session.get(Order, record_id) if record_id else None
        log = await session.get(CallLog, call_log_id) if call_log_id else None
        item = await session.get(CatalogItem, record.catalog_item_id) if record is not None and record.catalog_item_id else None
        return merchant, record, log, (item.name if item is not None else "")


async def _summary(call_log_id: str, event: str, known: str) -> str:
    """The call's summary: already written, written while we wait, or "" (sent without)."""
    if known or not call_log_id:
        return known or ""
    from app.services import summaries

    wait = URGENT_SUMMARY_WAIT_SECONDS if event == EVENT_URGENT else SUMMARY_WAIT_SECONDS
    text = await summaries.wait_for(call_log_id, wait)
    if text is None:
        # Not written by this process in time (or by another one): one last look.
        from app.models import CallLog

        async with sessions()() as session:
            log = await session.get(CallLog, call_log_id)
            text = str(getattr(log, "summary", "") or "")
    return text or ""


async def send_email(to: str, alert: compose.Alert) -> str:
    """``sent`` | ``skipped`` (no SMTP) | ``failed``."""
    if not smtp_ready():
        return "skipped"
    from app.core.email import send_email as smtp_send

    subject, body = compose.email(alert)
    try:
        await asyncio.to_thread(smtp_send, to=to, subject=subject, body=body)
        return "sent"
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("owner_alert_email_failed", error=str(exc)[:200])
        return "failed"


async def send_sms(merchant: Any, to: str, alert: compose.Alert) -> tuple[str, str]:
    """``(status, error)`` of the logged text (``sms.send`` skips an opted-out number)."""
    from app.services.sms.sending import KIND_ALERT, send

    message = await send(merchant, to, compose.sms(alert), kind=KIND_ALERT)
    return str(message.status or ""), str(getattr(message, "error", "") or "")


async def deliver(merchant_id: str, record_id: str, outcome: str, *, call_log_id: str = "") -> dict[str, str]:
    """Send the alert one agent outcome raises; returns ``{channel: status}``. Never raises."""
    try:
        merchant, record, log, item_name = await _load(merchant_id, record_id, call_log_id)
        if merchant is None:
            return {}
        event = event_for(outcome, str(getattr(record, "kind", "") or ""))
        channels = [
            channel for channel in channels_for(merchant, event)
            if (channel == CHANNEL_EMAIL and smtp_ready()) or (channel == CHANNEL_SMS and sms_ready())
        ]
        if not channels:
            return {}
        key = f"owner-alert:{merchant_id}:{record_id or call_log_id}:{event}:{call_log_id}"
        if await backends.call("hit", key, 1, float(DEDUPE_SECONDS)):
            return {}  # this outcome already alerted (written twice in one call)
        summary = await _summary(call_log_id, event, str(getattr(log, "summary", "") or ""))
        alert = compose.build(merchant, event=event, outcome=outcome, record=record, log=log, item_name=item_name, summary=summary)
        results: dict[str, str] = {}
        if CHANNEL_EMAIL in channels:
            results[CHANNEL_EMAIL] = await send_email(email_to(merchant), alert)
        if CHANNEL_SMS in channels:
            results[CHANNEL_SMS] = (await send_sms(merchant, settings_of(merchant)["sms_to"], alert))[0]
        await logger.ainfo("owner_alert", merchant_id=merchant_id, alert=event, outcome=outcome, results=results, summary=bool(summary))
        return results
    except Exception as exc:  # noqa: BLE001 — an alert never breaks a call
        await logger.awarning("owner_alert_failed", merchant_id=merchant_id, outcome=outcome, error=str(exc)[:200], error_type=type(exc).__name__)
        return {}


def schedule(merchant_id: str, record_id: str, outcome: str, *, call_log_id: str = "") -> None:
    """Alert the owner in the background (outcomes that never alert, or no loop: nothing). Never raises."""
    if not merchant_id or outcome not in OUTCOME_EVENT:
        return
    try:
        task = asyncio.get_running_loop().create_task(deliver(merchant_id, record_id or "", outcome, call_log_id=call_log_id))
    except RuntimeError:
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def send_test(merchant: Any) -> dict[str, dict[str, str]]:
    """"Send test alert": the sample to every channel with a recipient, whatever the events."""
    alert = compose.sample(merchant)
    results: dict[str, dict[str, str]] = {}
    to_email = email_to(merchant)
    if to_email:
        status = await send_email(to_email, alert)
        detail = {"skipped": "Email isn't set up on this server yet.", "failed": "The email couldn't be sent."}.get(status, f"Sent to {to_email}.")
        results[CHANNEL_EMAIL] = {"status": status, "detail": detail}
    to_sms = settings_of(merchant)["sms_to"]
    if to_sms:
        status, error = await send_sms(merchant, to_sms, alert)
        sent = status in ("queued", "sent", "delivered")
        results[CHANNEL_SMS] = {"status": status, "detail": f"Sent to {to_sms}." if sent else (error or "The text wasn't sent.")}
    return results


__all__ = ["DEDUPE_SECONDS", "SUMMARY_WAIT_SECONDS", "deliver", "schedule", "send_test"]
