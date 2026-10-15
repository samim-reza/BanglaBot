"""What a payment does to its booking: pure changes on an ``Order`` row (no I/O).

The payment skill leaves ``details["payment"]`` = ``{"mode", "method", "amount",
"currency", "status", "hold_minutes"}`` on the record. These helpers keep that
block and the record's ``payment_status`` / ``payment_ref`` / ``payment_url``
columns in step as the link is created, paid, released or refunded.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.models.order import OrderStatus
from app.services.payments.base import STATUS_EXPIRED, STATUS_PAID, STATUS_PENDING, PaymentError, currency_code, money

RECORD_NOT_REQUIRED = "not_required"
RECORD_AT_VENUE = "at_venue"
RECORD_PAYMENT_STATUSES = (RECORD_NOT_REQUIRED, RECORD_AT_VENUE, "pending", "paid", "failed", "refunded", "expired")
MODE_ONLINE_REQUIRED = "online_required"
#: Bounds on how long an unpaid online-required booking is held (minutes).
MIN_HOLD_MINUTES, MAX_HOLD_MINUTES = 5, 7 * 24 * 60


def _status(record: Any) -> str:
    value = getattr(record, "status", "")
    return str(getattr(value, "value", value) or "")


def _iso(value: datetime | None) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


def _note(record: Any, text: str, now: datetime) -> None:
    line = f"[{now.strftime('%Y-%m-%d %H:%M')}] {text}"
    existing = str(getattr(record, "notes", "") or "")
    record.notes = f"{existing}\n{line}".strip() if existing else line


def payment_details(record: Any) -> dict[str, Any]:
    details = getattr(record, "details", None) or {}
    block = details.get("payment") if isinstance(details, dict) else None
    return dict(block) if isinstance(block, dict) else {}


def _update_details(record: Any, **changes: Any) -> None:
    details = dict(getattr(record, "details", None) or {})
    block = dict(details.get("payment") or {}) if isinstance(details.get("payment"), dict) else {}
    block.update({key: value for key, value in changes.items() if value is not None})
    details["payment"] = block
    record.details = details  # a new dict, so the JSONB change is tracked


def wants_link(record: Any) -> bool:
    """The caller chose (or must make) an online payment and no link exists yet."""
    block = payment_details(record)
    if block.get("method") != "online" or block.get("status") not in ("link_pending", "", None):
        return False
    if getattr(record, "payment_ref", "") or getattr(record, "payment_status", "") in (STATUS_PENDING, STATUS_PAID):
        return False
    return _status(record) != OrderStatus.cancelled.value


def pays_at_venue(record: Any) -> bool:
    return payment_details(record).get("method") == "at_venue" and getattr(record, "payment_status", "") in ("", RECORD_NOT_REQUIRED)


def link_amount(record: Any) -> tuple[Decimal, str]:
    """``(amount, currency)`` the link asks for: the skill's amount, else the record total."""
    block = payment_details(record)
    raw = block.get("amount") or getattr(record, "total_amount", 0) or 0
    amount = money(raw)
    if amount <= 0:
        raise PaymentError("nothing to pay")
    return amount, currency_code(block.get("currency") or getattr(record, "currency", ""), "USD")


def holds_slot(record: Any) -> bool:
    """An online-required booking waits (``pending``) for its payment."""
    return payment_details(record).get("mode") == MODE_ONLINE_REQUIRED and _status(record) == OrderStatus.pending.value


def hold_minutes(record: Any) -> int:
    try:
        minutes = int(payment_details(record).get("hold_minutes") or 30)
    except (TypeError, ValueError):
        minutes = 30
    return max(MIN_HOLD_MINUTES, min(MAX_HOLD_MINUTES, minutes))


def apply_at_venue(record: Any) -> None:
    record.payment_status = RECORD_AT_VENUE


def apply_link(record: Any, payment: Any) -> None:
    record.payment_status = STATUS_PENDING
    record.payment_ref = str(payment.id)
    record.payment_url = str(payment.url or "")
    _update_details(
        record,
        status=STATUS_PENDING,
        url=str(payment.url or ""),
        payment_id=str(payment.id),
        provider=str(payment.provider or ""),
        expires_at=_iso(payment.expires_at) or None,
        hold_until=_iso(payment.hold_until) or None,
    )


def apply_paid(record: Any, payment: Any, now: datetime) -> str:
    """Mark the booking paid; returns the new record status when it changed ("" otherwise)."""
    record.payment_status = STATUS_PAID
    if not getattr(record, "payment_ref", ""):
        record.payment_ref = str(payment.id)
    _update_details(record, status=STATUS_PAID, paid_at=now.isoformat(), payment_id=str(payment.id))
    status = _status(record)
    amount = f"{payment.amount} {payment.currency}".strip()
    if status == OrderStatus.pending.value and payment_details(record).get("mode") == MODE_ONLINE_REQUIRED:
        record.status = OrderStatus.confirmed
        _note(record, f"Payment received ({amount}) - booking confirmed", now)
        return OrderStatus.confirmed.value
    if status == OrderStatus.cancelled.value and payment_details(record).get("released_at"):
        # Paid after the hold ran out: the slot may be gone, someone has to look.
        record.status = OrderStatus.needs_review
        _note(record, f"Payment received ({amount}) after the hold was released - check the slot", now)
        return OrderStatus.needs_review.value
    _note(record, f"Payment received ({amount})", now)
    return ""


def apply_release(record: Any, now: datetime) -> None:
    """The hold ran out unpaid: free the slot."""
    record.status = OrderStatus.cancelled
    record.payment_status = STATUS_EXPIRED
    _update_details(record, status=STATUS_EXPIRED, released_at=now.isoformat())
    _note(record, f"Payment not received within {hold_minutes(record)} minutes - booking released", now)


def apply_payment_status(record: Any, status: str) -> None:
    """failed / refunded / expired (link) without touching the booking itself."""
    record.payment_status = status
    _update_details(record, status=status)


__all__ = [
    "MODE_ONLINE_REQUIRED",
    "RECORD_AT_VENUE",
    "RECORD_NOT_REQUIRED",
    "RECORD_PAYMENT_STATUSES",
    "apply_at_venue",
    "apply_link",
    "apply_paid",
    "apply_payment_status",
    "apply_release",
    "hold_minutes",
    "holds_slot",
    "link_amount",
    "pays_at_venue",
    "payment_details",
    "wants_link",
]
