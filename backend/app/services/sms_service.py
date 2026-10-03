"""SMS confirmations and reminders over Telnyx Messaging.

When the agent books, moves or cancels something (or a COD order is confirmed),
the customer gets a short text with the details; appointments, visits and
viewings also get a reminder ``reminder_hours`` before they start. Every text is
logged in ``messages`` with its delivery status (Telnyx receipts update it).

Account settings live in ``merchants.sms_settings``::

    {"enabled": true, "on_booking": true, "on_change": true, "reminder_hours": 24}
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.core.regions import normalize_phone, region_of
from app.db.session import AsyncSessionLocal
from app.flows.timefmt import business_tz, date_phrase
from app.models import CatalogItem, Merchant, Message, Order, OrderStatus
from app.services import telnyx
from app.voice.languages import normalize_language

logger = structlog.get_logger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {"enabled": False, "on_booking": True, "on_change": True, "reminder_hours": 24}
#: Agent outcome → the text it triggers.
OUTCOME_KIND = {"booked": "confirmation", "rescheduled": "change", "cancelled": "cancellation", "lead": "lead", "confirmed": "confirmation"}
LIVE = (OrderStatus.pending, OrderStatus.confirmed)


def settings_of(merchant: Any) -> dict[str, Any]:
    stored = getattr(merchant, "sms_settings", None)
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(stored, dict):
        merged.update({key: value for key, value in stored.items() if key in DEFAULT_SETTINGS and value is not None})
    return merged


def platform_ready() -> bool:
    settings = get_settings()
    return bool(
        settings.sms_enabled
        and settings.telnyx_api_key
        and (settings.telnyx_sms_from or settings.telnyx_from_number)
    )


def planned_kind(merchant: Any, outcome: str, *, record_kind: str = "", phone: str = "") -> str | None:
    """Which text an outcome sends to this account's customer, or None (pure; no I/O)."""
    config = settings_of(merchant)
    if not config["enabled"] or not phone or not platform_ready():
        return None
    kind = OUTCOME_KIND.get(outcome)
    if kind is None:
        return None
    if outcome == "confirmed" and record_kind != "order":
        # A reminder call's "yes, I'll come" needs no extra text; an e-commerce confirmation does.
        return None
    if kind in ("confirmation", "lead") and not config["on_booking"]:
        return None
    if kind in ("change", "cancellation") and not config["on_change"]:
        return None
    return kind


# --------------------------------------------------------------------------- composing
def _local(record: Any, merchant: Any) -> datetime | None:
    start = getattr(record, "scheduled_at", None)
    if not isinstance(start, datetime):
        return None
    return start.astimezone(business_tz(getattr(merchant, "timezone", "") or region_of(merchant).timezone))


def _when(record: Any, merchant: Any, lang: str) -> str:
    """"Mon, Oct 5 at 10:40 AM" (US style) / "Mon, 5 Oct at 10:40 AM" / Bangla date + 24 h time."""
    local = _local(record, merchant)
    if local is None:
        return ""
    if lang == "bn":
        return f"{date_phrase(local.date(), None, 'bn')}, {local.strftime('%H:%M')}"
    day = local.strftime("%a, %b ") + str(local.day) if region_of(merchant).date_style == "mdy" else local.strftime("%a, ") + f"{local.day} " + local.strftime("%b")
    return f"{day} at {_clock(local.time())}"


def _clock(value: Any) -> str:
    text = value.strftime("%I:%M %p").lstrip("0")
    return text.replace(":00 ", " ")


def _window(record: Any, merchant: Any) -> str:
    """The booked arrival window, e.g. "12 PM–4 PM"."""
    details = getattr(record, "details", None) or {}
    key = details.get("time_window") if isinstance(details, dict) else ""
    if not key:
        return ""
    windows = (getattr(merchant, "vertical_config", None) or {}).get("time_windows") or [
        {"key": "morning", "start": "09:00", "end": "12:00"},
        {"key": "afternoon", "start": "12:00", "end": "15:00"},
        {"key": "evening", "start": "15:00", "end": "18:00"},
    ]
    from app.flows.timefmt import parse_time

    for window in windows:
        if isinstance(window, dict) and window.get("key") == key:
            start, end = parse_time(window.get("start")), parse_time(window.get("end"))
            if start and end:
                return f"{_clock(start)}–{_clock(end)}"
    return ""


def _money(amount: Any, currency: str) -> str:
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    symbol = {"USD": "$", "CAD": "CA$", "AUD": "A$", "GBP": "£", "EUR": "€", "INR": "₹", "BDT": "৳"}.get(currency.upper(), f"{currency} ")
    return f"{symbol}{value:,.0f}" if value == int(value) else f"{symbol}{value:,.2f}"


def compose(kind: str, record: Any, merchant: Any, *, item_name: str = "") -> str:
    """The text for one event, short enough for one or two SMS segments."""
    lang = normalize_language(getattr(merchant, "language", None))
    business = str(getattr(merchant, "business_name", "") or "")
    phone = str(getattr(merchant, "support_phone", "") or getattr(merchant, "phone", "") or "")
    call = (f" Call {phone} to change." if lang != "bn" else f" পরিবর্তনে কল করুন {phone}।") if phone else ""
    record_kind = str(getattr(record, "kind", "") or "")
    when = _when(record, merchant, lang)
    window = _window(record, merchant)
    if window and when:
        # Visits are booked as an arrival window, not a minute.
        when = when.rsplit(" at ", 1)[0] + f", {window}" if lang != "bn" else when.rsplit(",", 1)[0] + f", {window}"
    name = item_name or str(getattr(record, "items_summary", "") or "")
    address = str(getattr(record, "address", "") or "")
    amount = _money(getattr(record, "total_amount", 0), str(getattr(record, "currency", "") or getattr(merchant, "currency", "") or "USD"))
    ref = str(getattr(record, "order_ref", "") or "")

    if lang == "bn":
        texts = {
            ("appointment", "confirmation"): f"{business}: {when} {name} এর সাথে আপনার অ্যাপয়েন্টমেন্ট কনফার্ম হয়েছে।{call}",
            ("appointment", "change"): f"{business}: আপনার অ্যাপয়েন্টমেন্ট {when} এ সরানো হয়েছে ({name}).{call}",
            ("appointment", "cancellation"): f"{business}: {when} এর অ্যাপয়েন্টমেন্ট বাতিল হয়েছে।",
            ("appointment", "reminder"): f"রিমাইন্ডার — {business}: {when} {name} এর সাথে অ্যাপয়েন্টমেন্ট।{call}",
            ("booking", "confirmation"): f"{business}: {name} এর বুকিং কনফার্ম — {when}, {address}।{call}",
            ("booking", "change"): f"{business}: আপনার {name} ভিজিট {when} এ সরানো হয়েছে।{call}",
            ("booking", "cancellation"): f"{business}: আপনার {name} বুকিং বাতিল হয়েছে।",
            ("booking", "reminder"): f"রিমাইন্ডার — {business}: {when} টেকনিশিয়ান আসবেন ({name})।{call}",
            ("lead", "confirmation"): f"{business}: আপনার সাইট ভিজিট কনফার্ম — {when}। প্রতিনিধি আগের দিন ফোন করবেন।",
            ("lead", "lead"): f"{business} এ ফোন করার জন্য ধন্যবাদ। আমাদের প্রতিনিধি শীঘ্রই যোগাযোগ করবেন।",
            ("lead", "reminder"): f"রিমাইন্ডার — {business}: {when} সাইট ভিজিট।",
            ("order", "confirmation"): f"{business}: ধন্যবাদ! আপনার অর্ডার {ref} ({amount}) কনফার্ম হয়েছে।".replace(" ()", ""),
            ("order", "cancellation"): f"{business}: আপনার অর্ডার {ref} বাতিল করা হয়েছে।",
            ("message", "lead"): f"{business}: আপনার বার্তা পেয়েছি, প্রতিনিধি শীঘ্রই ফোন করবেন।",
        }
    else:
        texts = {
            ("appointment", "confirmation"): f"{business}: your appointment with {name} is confirmed for {when}.{call}",
            ("appointment", "change"): f"{business}: your appointment with {name} has moved to {when}.{call}",
            ("appointment", "cancellation"): f"{business}: your appointment on {when} has been cancelled. Call us any time to book again.",
            ("appointment", "reminder"): f"Reminder from {business}: appointment with {name} on {when}.{call}",
            ("booking", "confirmation"): f"{business}: your {name} visit is booked for {when}" + (f" at {address}" if address else "") + (f". Call-out charge {amount}" if amount else "") + f". The technician calls before arriving.{call}",
            ("booking", "change"): f"{business}: your {name} visit has moved to {when}.{call}",
            ("booking", "cancellation"): f"{business}: your {name} booking has been cancelled.",
            ("booking", "reminder"): f"Reminder from {business}: your {name} visit is on {when}.{call}",
            ("lead", "confirmation"): f"{business}: your viewing" + (f" of {name}" if name and " · " not in name else "") + f" is confirmed for {when}. Our agent will call the day before with the meeting point.",
            ("lead", "change"): f"{business}: your viewing has moved to {when}.",
            ("lead", "lead"): f"Thanks for calling {business}! One of our agents will be in touch shortly.",
            ("lead", "reminder"): f"Reminder from {business}: your property viewing is on {when}.",
            ("order", "confirmation"): f"{business}: thanks! Your order" + (f" {ref}" if ref else "") + (f" ({amount})" if amount else "") + " is confirmed and will ship soon.",
            ("order", "cancellation"): f"{business}: your order" + (f" {ref}" if ref else "") + " has been cancelled as requested.",
            ("message", "lead"): f"Thanks for contacting {business} — we got your message and a team member will call you back.",
        }
    text = " ".join((texts.get((record_kind, kind)) or texts.get(("appointment", kind)) or "").split())
    if lang != "bn":
        # One non-GSM character (an en dash, a curly quote) turns the whole text into
        # 70-character UCS-2 segments — 2-3x the price. Keep English texts plain ASCII.
        text = text.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return text


def segments(body: str) -> int:
    """SMS segments (GSM-7: 160/153 per part; anything else: UCS-2, 70/67)."""
    gsm = all(ord(ch) < 128 for ch in body)
    single, multi = (160, 153) if gsm else (70, 67)
    length = len(body)
    return 1 if length <= single else -(-length // multi)


# --------------------------------------------------------------------------- sending
def _sms_status_url(message_id: str) -> str | None:
    base = str(get_settings().public_base_url or "").rstrip("/")
    return f"{base}/telnyx/sms-status/{message_id}" if base.startswith("https://") else None


async def send(merchant: Merchant, to: str, body: str, *, kind: str, order_id: str | None = None) -> Message:
    """Send one SMS (logged whatever happens). Never raises for delivery problems."""
    to_number = normalize_phone(to, region_of(merchant))
    async with AsyncSessionLocal() as session:
        message = Message(
            merchant_id=merchant.id, order_id=order_id, kind=kind, to_number=to_number, body=body,
            status="queued", segments=segments(body),
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
    if not platform_ready():
        await _update(message.id, status="skipped", error="SMS is not configured on the platform (Telnyx API key / sender).")
        message.status = "skipped"
        return message
    callback = _sms_status_url(message.id)
    try:
        sid = await telnyx.send_sms(to=to_number, text=body, webhook_url=callback, from_number=telnyx.number_for(merchant))
        await _update(message.id, status="sent", provider_sid=sid)
        message.status, message.provider_sid = "sent", sid
        await logger.ainfo("sms_sent", merchant_id=merchant.id, kind=kind, to=to_number, sid=sid)
    except Exception as exc:  # noqa: BLE001 — a failed text never breaks the call / request
        detail = getattr(exc, "detail", None) or str(exc)
        await _update(message.id, status="failed", error=str(detail)[:500])
        message.status, message.error = "failed", str(detail)[:500]
        await logger.awarning("sms_failed", merchant_id=merchant.id, kind=kind, to=to_number, error=str(detail)[:200])
    return message


async def _update(message_id: str, **fields: Any) -> None:
    async with AsyncSessionLocal() as session:
        message = await session.get(Message, message_id)
        if message is None:
            return
        for key, value in fields.items():
            setattr(message, key, value)
        message.updated_at = utcnow()
        await session.commit()


#: Telnyx recipient status → ours.
TELNYX_STATUS = {
    "queued": "queued",
    "sending": "sent",
    "sent": "sent",
    "delivery_unconfirmed": "sent",
    "delivered": "delivered",
    "read": "read",
    "expired": "undelivered",
    "delivery_failed": "undelivered",
    "sending_failed": "failed",
}


async def apply_status(message_id: str, status: str, error: str = "", *, provider_sid: str = "") -> None:
    """Telnyx delivery receipt, matched by our message id or else by Telnyx's."""
    mapped = TELNYX_STATUS.get(str(status or "").lower())
    if mapped is None:
        return
    if not message_id and provider_sid:
        async with AsyncSessionLocal() as session:
            message_id = str(await session.scalar(select(Message.id).where(Message.provider_sid == provider_sid)) or "")
    if not message_id:
        return
    fields: dict[str, Any] = {"status": mapped}
    if error:
        fields["error"] = str(error)[:500]
    await _update(message_id, **fields)


async def _item_name(session: Any, item_id: str | None) -> str:
    if not item_id:
        return ""
    item = await session.get(CatalogItem, item_id)
    return item.name if item is not None else ""


async def after_outcome(merchant_id: str, record_id: str, outcome: str) -> None:
    """The text a call / chat outcome triggers (confirmation, change, cancellation…)."""
    try:
        async with AsyncSessionLocal() as session:
            merchant = await session.get(Merchant, merchant_id)
            record = await session.get(Order, record_id) if record_id else None
            if merchant is None or record is None:
                return
            kind = planned_kind(merchant, outcome, record_kind=record.kind or "", phone=record.customer_phone or "")
            if kind is None:
                return
            # The same outcome can be written twice (an order confirmed, then its address
            # checked): one text per record and kind within a few minutes.
            recent = await session.scalar(
                select(Message.id).where(
                    Message.order_id == record.id,
                    Message.kind == kind,
                    Message.created_at >= utcnow() - timedelta(minutes=15),
                ).limit(1)
            )
            if recent:
                return
            body = compose(kind, record, merchant, item_name=await _item_name(session, record.catalog_item_id))
        if body:
            await send(merchant, record.customer_phone, body, kind=kind, order_id=record.id)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("sms_after_outcome_failed", record_id=record_id, error=str(exc))


# --------------------------------------------------------------------------- reminders
async def send_due_reminders(now: datetime | None = None) -> int:
    """Text every live appointment / visit / viewing whose reminder time has come.

    A record is reminded once (``details.sms_reminder_at``), and only if it was
    booked before its reminder window opened — a same-day booking already got
    its confirmation text."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    async with AsyncSessionLocal() as session:
        merchants = list(await session.scalars(select(Merchant).where(Merchant.active.is_(True))))
    for merchant in merchants:
        config = settings_of(merchant)
        hours = int(config.get("reminder_hours") or 0)
        if not config["enabled"] or hours <= 0:
            continue
        horizon = now + timedelta(hours=hours)
        async with AsyncSessionLocal() as session:
            rows = list(
                await session.scalars(
                    select(Order).where(
                        Order.merchant_id == merchant.id,
                        Order.scheduled_at.is_not(None),
                        Order.scheduled_at > now,
                        Order.scheduled_at <= horizon,
                        Order.status.in_(LIVE),
                        Order.kind.in_(("appointment", "booking", "lead")),
                    )
                )
            )
            due: list[tuple[Order, str]] = []
            for row in rows:
                details = dict(row.details or {})
                if details.get("sms_reminder_at") or not row.customer_phone:
                    continue
                created = row.created_at or now
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if row.scheduled_at - created < timedelta(hours=hours):
                    continue
                details["sms_reminder_at"] = now.isoformat()
                row.details = details
                due.append((row, await _item_name(session, row.catalog_item_id)))
            await session.commit()
        for row, item_name in due:
            body = compose("reminder", row, merchant, item_name=item_name)
            if body:
                await send(merchant, row.customer_phone, body, kind="reminder", order_id=row.id)
                sent += 1
    return sent


async def run_reminders() -> None:
    """Lifespan task: send due reminders every few minutes."""
    interval = max(60, int(get_settings().sms_reminder_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        if not platform_ready():
            continue
        try:
            count = await send_due_reminders()
            if count:
                await logger.ainfo("sms_reminders_sent", count=count)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("sms_reminders_failed", error=str(exc))


__all__ = [
    "DEFAULT_SETTINGS",
    "after_outcome",
    "apply_status",
    "compose",
    "planned_kind",
    "platform_ready",
    "run_reminders",
    "segments",
    "send",
    "send_due_reminders",
    "settings_of",
]
