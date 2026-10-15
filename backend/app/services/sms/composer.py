"""Composing texts: per vertical / record kind / event wording in English and Bangla,
local dates and arrival windows, money, and SMS segment counting."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.regions import region_of
from app.flows.timefmt import business_tz, date_phrase
from app.services.sms_texts import vertical_text
from app.voice.languages import normalize_language


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
    special = vertical_text(
        str(getattr(merchant, "vertical", "") or ""),
        record_kind,
        kind,
        {"business": business, "when": when, "name": name, "address": address, "amount": amount, "ref": ref, "call": call,
         "details": getattr(record, "details", None) or {}},
        lang,
    )
    text = " ".join((special or texts.get((record_kind, kind)) or texts.get(("appointment", kind)) or "").split())
    if lang != "bn":
        # One non-GSM character (an en dash, a curly quote) turns the whole text into
        # 70-character UCS-2 segments — 2-3x the price. Keep English texts plain ASCII.
        text = text.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    pay_url = str(getattr(record, "payment_url", "") or "")
    if text and pay_url and kind == "confirmation" and getattr(record, "payment_status", "") == "pending":
        # The booking's online payment link (app.services.payments creates it before this text).
        text += f" পেমেন্ট: {pay_url}" if lang == "bn" else f" Pay here: {pay_url}"
    return text


def segments(body: str) -> int:
    """SMS segments (GSM-7: 160/153 per part; anything else: UCS-2, 70/67)."""
    gsm = all(ord(ch) < 128 for ch in body)
    single, multi = (160, 153) if gsm else (70, 67)
    length = len(body)
    return 1 if length <= single else -(-length // multi)
