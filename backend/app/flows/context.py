"""Everything a flow may know about the call it is running — plain data, no I/O.

The service layer builds a :class:`CallContext` when a call starts (from the
database, or from the in-process snapshot taken when an outbound call was
placed) and the flow reads it on every turn. Rows are duck-typed: ORM objects
in production, small dataclasses in tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.regions import Region, get_region
from app.flows.scheduling import slot_key
from app.flows.timefmt import business_tz, local_now

DIRECTION_OUTBOUND = "outbound"
DIRECTION_INBOUND = "inbound"
DIRECTIONS = (DIRECTION_OUTBOUND, DIRECTION_INBOUND)


@dataclass(frozen=True)
class CatalogEntry:
    """One bookable/sellable thing of the business: a doctor, a listing, a service."""

    id: str
    #: Short reference the model uses in tool calls ("D1", "P2", "S3").
    ref: str
    kind: str
    name: str
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.data.get(key, default)
        return default if value in (None, "") else value


def _norm(text: Any) -> str:
    lowered = str(text or "").lower()
    lowered = re.sub(r"(?:^|\s)(?:dr|ডা|ডাঃ|ডাক্তার|doctor)\.?\s*", " ", lowered)
    return " ".join(re.sub(r"[^\w\s]", " ", lowered).split())


@dataclass
class CallContext:
    merchant: Any
    #: The record this call is about (outbound), or the one an inbound call created/found.
    record: Any | None = None
    direction: str = DIRECTION_OUTBOUND
    #: Caller ID of an inbound call (E.164 / local); empty when unknown (browser test).
    caller_number: str = ""
    catalog: list[CatalogEntry] = field(default_factory=list)
    #: :func:`scheduling.slot_key` → live bookings in that slot (snapshot at call start).
    booked: dict[str, int] = field(default_factory=dict)
    #: Busy times from the business's calendars: catalog item id (or "" for the whole
    #: business) → (start, end) intervals. Slots overlapping them are never offered.
    busy: dict[str, list[tuple[datetime, datetime]]] = field(default_factory=dict)
    #: The caller's open records (upcoming appointments, bookings) for inbound calls.
    caller_records: list[Any] = field(default_factory=list)
    #: Business-local "now" (defaults to the account's time zone).
    now: datetime | None = None
    #: Lines composed ahead of time (e.g. the order-confirmation sentence), by key.
    prepared: dict[str, str] = field(default_factory=dict)
    #: A test call from the portal (browser voice or text chat).
    test: bool = False
    #: ``voice`` (phone / browser call) or ``chat`` (text: test console, website widget).
    channel: str = "voice"

    def __post_init__(self) -> None:
        if self.now is None:
            self.now = local_now(business_tz(self.timezone))

    # ---- shortcuts --------------------------------------------------------
    @property
    def region(self) -> Region:
        return get_region(self.merchant_value("region", None))

    @property
    def timezone(self) -> str:
        return str(self.merchant_value("timezone", "") or self.region.timezone)

    @property
    def currency(self) -> str:
        return str(self.merchant_value("currency", "") or self.region.currency).upper()

    @property
    def emergency_number(self) -> str:
        return str(self.merchant_value("emergency_number", "") or self.region.emergency)

    @property
    def month_first(self) -> bool:
        return self.region.date_style == "mdy"

    @property
    def saturday_first(self) -> bool:
        """List weekdays Saturday-first (the Bangladeshi week) or Monday-first."""
        return self.region.code == "BD"

    @property
    def chat(self) -> bool:
        return self.channel == "chat"

    def say_number(self, value: Any, language: str) -> str:
        """A phone / service number: digit words on a call, plain digits in a chat."""
        from app.flows.timefmt import short_number, spoken_digits

        text = str(value or "").strip()
        if self.chat:
            return text
        digits = "".join(ch for ch in text if ch.isdigit())
        return short_number(text, language) if len(digits) <= 4 else spoken_digits(text, language)

    @property
    def order(self) -> Any | None:
        return self.record

    @property
    def inbound(self) -> bool:
        return self.direction == DIRECTION_INBOUND

    @property
    def today(self):
        assert self.now is not None
        return self.now.date()

    @property
    def config(self) -> dict[str, Any]:
        value = getattr(self.merchant, "vertical_config", None)
        return dict(value) if isinstance(value, dict) else {}

    def merchant_value(self, name: str, default: Any = "") -> Any:
        value = getattr(self.merchant, name, None) if self.merchant is not None else None
        return default if value in (None, "") else value

    def record_value(self, name: str, default: Any = "") -> Any:
        value = getattr(self.record, name, None) if self.record is not None else None
        return default if value in (None, "") else value

    def record_details(self) -> dict[str, Any]:
        value = getattr(self.record, "details", None) if self.record is not None else None
        return dict(value) if isinstance(value, dict) else {}

    # ---- catalog ------------------------------------------------------------
    def items(self, kind: str | None = None) -> list[CatalogEntry]:
        return [item for item in self.catalog if kind is None or item.kind == kind]

    def item_by_id(self, item_id: Any) -> CatalogEntry | None:
        wanted = str(item_id or "")
        return next((item for item in self.catalog if item.id == wanted), None) if wanted else None

    def find_items(self, value: Any, kind: str | None = None, *, fields: tuple[str, ...] = ()) -> list[CatalogEntry]:
        """Resolve what the model saved — a ref ("D2"), an id, or a name — to catalog entries.

        Exact ref / id / name wins; otherwise every entry whose name (or one of
        ``fields``, e.g. a doctor's specialty) contains the words is returned, so
        the caller can be asked to choose when several match.
        """
        text = str(value or "").strip()
        if not text:
            return []
        pool = self.items(kind)
        upper = text.upper()
        for item in pool:
            if item.ref.upper() == upper or item.id == text:
                return [item]
        wanted = _norm(text)
        if not wanted:
            return []
        exact = [item for item in pool if _norm(item.name) == wanted]
        if exact:
            return exact
        tokens = wanted.split()
        matches: list[CatalogEntry] = []
        for item in pool:
            haystack = " ".join([_norm(item.name)] + [_norm(item.get(name, "")) for name in fields])
            if wanted in haystack or all(token in haystack.split() or token in haystack for token in tokens):
                matches.append(item)
        return matches

    # ---- the booking snapshot ---------------------------------------------------
    def taken(self, item_id: str | None, start: datetime) -> int:
        return int(self.booked.get(slot_key(item_id, start), 0))

    def busy_for(self, item_id: str | None = None) -> list[tuple[datetime, datetime]]:
        """Busy times for a resource: its own calendar plus the whole business's."""
        own = self.busy.get(item_id, []) if item_id else []
        return [*own, *self.busy.get("", [])]

    def mark_booked(self, item_id: str | None, start: datetime, count: int = 1) -> None:
        key = slot_key(item_id, start)
        self.booked[key] = int(self.booked.get(key, 0)) + count


__all__ = [
    "DIRECTIONS",
    "DIRECTION_INBOUND",
    "DIRECTION_OUTBOUND",
    "CallContext",
    "CatalogEntry",
]
