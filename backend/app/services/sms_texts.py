"""Vertical-specific SMS wording (checked before the per-record-kind texts in ``sms_service.compose``).

A restaurant order isn't "shipping", a table booking has no "technician", and a
custom business's lead isn't a property viewing — these say the right thing.
English texts stay plain ASCII (one non-GSM character triples the SMS price).
"""

from __future__ import annotations

from typing import Any


def vertical_text(vertical: str, record_kind: str, kind: str, v: dict[str, Any], lang: str) -> str:
    """``v``: business, when, name, address, amount, ref, call, details. Empty = use the generic text."""
    details = v.get("details") or {}
    b, when, call = v["business"], v["when"], v["call"]
    if lang == "bn":
        return _bangla(vertical, record_kind, kind, v, details)
    if vertical == "restaurant":
        if record_kind == "order" and kind == "confirmation":
            total = f" ({v['amount']})" if v["amount"] else ""
            if details.get("fulfillment") == "delivery":
                return f"{b}: thanks! Your order{total} is confirmed and will be delivered" + (f" around {when}" if when else "") + f".{call}"
            return f"{b}: thanks! Your order{total} is confirmed" + (f" - ready for pickup around {when}" if when else "") + f".{call}"
        if record_kind == "order" and kind == "cancellation":
            return f"{b}: your order has been cancelled."
        if record_kind == "booking":
            party = details.get("party_size")
            table = f"table for {party}" if party else "table"
            return {
                "confirmation": f"{b}: your {table} is booked for {when}. We hold it for 15 minutes.{call}",
                "change": f"{b}: your {table} has moved to {when}.{call}",
                "cancellation": f"{b}: your table booking has been cancelled.",
                "reminder": f"Reminder from {b}: your {table} is booked for {when}.{call}",
            }.get(kind, "")
    if vertical == "salon" and record_kind == "booking":
        name = v["name"] or "appointment"
        return {
            "confirmation": f"{b}: your {name} is booked for {when}.{call}",
            "change": f"{b}: your {name} has moved to {when}.{call}",
            "cancellation": f"{b}: your {name} booking has been cancelled.",
            "reminder": f"Reminder from {b}: your {name} is on {when}.{call}",
        }.get(kind, "")
    if vertical == "vet" and record_kind == "appointment":
        pet = (details.get("intake") or {}).get("pet_name") or details.get("pet_name") or ""
        whose = f"{pet}'s" if pet else "your pet's"
        return {
            "confirmation": f"{b}: {whose} appointment" + (f" with {v['name']}" if v["name"] else "") + f" is confirmed for {when}.{call}",
            "reminder": f"Reminder from {b}: {whose} appointment is on {when}.{call}",
        }.get(kind, "")
    if vertical == "custom":
        if record_kind == "booking":
            return {
                "confirmation": f"{b}: your booking" + (f" ({v['name']})" if v["name"] else "") + f" is confirmed for {when}.{call}",
                "change": f"{b}: your booking has moved to {when}.{call}",
                "cancellation": f"{b}: your booking has been cancelled.",
                "reminder": f"Reminder from {b}: your booking is on {when}.{call}",
            }.get(kind, "")
        if record_kind in ("lead", "message") and kind == "lead":
            return f"Thanks for contacting {b} - we got your details and will be in touch shortly."
    return ""


def _bangla(vertical: str, record_kind: str, kind: str, v: dict[str, Any], details: dict[str, Any]) -> str:
    b, when, call = v["business"], v["when"], v["call"]
    if vertical == "restaurant" and record_kind == "order" and kind == "confirmation":
        how = "ডেলিভারি দেওয়া হবে" if details.get("fulfillment") == "delivery" else "পিকআপের জন্য তৈরি থাকবে"
        return f"{b}: ধন্যবাদ! আপনার অর্ডার কনফার্ম হয়েছে, {when} নাগাদ {how}।{call}"
    if vertical == "restaurant" and record_kind == "booking" and kind == "confirmation":
        return f"{b}: আপনার টেবিল বুক হয়েছে — {when}। ১৫ মিনিট ধরে রাখা হবে।{call}"
    if vertical in ("salon", "custom") and record_kind == "booking" and kind == "confirmation":
        return f"{b}: আপনার বুকিং কনফার্ম হয়েছে — {when}।{call}"
    if vertical == "custom" and kind == "lead":
        return f"{b} এ যোগাযোগের জন্য ধন্যবাদ। আমরা শীঘ্রই যোগাযোগ করব।"
    return ""


__all__ = ["vertical_text"]
