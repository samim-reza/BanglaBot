"""Validate portal input against a vertical's field specs.

The same :class:`~app.verticals.base.FieldSpec` lists that render the portal's
record / catalog / settings forms are enforced here, so a field the UI shows
is exactly a field the API accepts — with the same types.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.flows.timefmt import normalize_days, parse_date, parse_time
from app.verticals.base import FieldSpec, Vertical

MAX_TEXT = 2000


class FieldError(ValueError):
    def __init__(self, key: str, message: str) -> None:
        super().__init__(f"{key}: {message}")
        self.key = key


def _number(value: Any, key: str) -> float | int:
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise FieldError(key, "must be a number") from exc
    if number < 0:
        raise FieldError(key, "must not be negative")
    return int(number) if number == number.to_integral_value() else float(number)


def coerce(spec: FieldSpec, value: Any, *, tz: tzinfo | None = None) -> Any:
    """One value → its stored form (``None`` for an empty optional value)."""
    if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value and spec.type not in ("days", "list", "multiselect")):
        return None
    kind = spec.type
    key = spec.key
    if kind in ("text", "textarea", "phone"):
        text = " ".join(str(value).split()) if kind != "textarea" else str(value).strip()
        if kind == "phone" and len(re.sub(r"\D", "", text)) < 6:
            raise FieldError(key, "does not look like a phone number")
        return text[:MAX_TEXT]
    if kind in ("money", "number"):
        return _number(value, key)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if kind == "date":
        parsed = value if isinstance(value, date) else parse_date(value)
        if parsed is None:
            raise FieldError(key, "must be a date (YYYY-MM-DD)")
        return parsed.isoformat()
    if kind == "time":
        parsed = parse_time(value)
        if parsed is None:
            raise FieldError(key, "must be a time (HH:MM)")
        return parsed.strftime("%H:%M")
    if kind == "datetime":
        if isinstance(value, datetime):
            parsed_dt = value
        else:
            try:
                parsed_dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError as exc:
                raise FieldError(key, "must be a date and time") from exc
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=tz or timezone.utc)
        return parsed_dt
    if kind == "select":
        allowed = {option for option, _ in spec.options}
        text = str(value).strip()
        if allowed and text not in allowed:
            raise FieldError(key, f"must be one of {', '.join(sorted(allowed))}")
        return text
    if kind == "multiselect":
        allowed = {option for option, _ in spec.options}
        items = [str(item).strip() for item in (value if isinstance(value, list) else str(value).split(","))]
        return [item for item in items if item and (not allowed or item in allowed)]
    if kind == "days":
        items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value))
        return normalize_days(items)
    if kind == "list":
        items = value if isinstance(value, list) else re.split(r"[\n,;]+", str(value))
        return [" ".join(str(item).split()) for item in items if str(item).strip()][:100]
    if kind == "catalog":
        return str(value).strip()
    return value


def clean(specs: Iterable[FieldSpec], data: dict[str, Any], *, partial: bool = False, tz: tzinfo | None = None) -> dict[str, Any]:
    """Validated values for the known fields in ``data``; required fields enforced unless ``partial``."""
    out: dict[str, Any] = {}
    for spec in specs:
        if spec.key not in data:
            if spec.required and not partial:
                raise FieldError(spec.key, "is required")
            continue
        value = coerce(spec, data.get(spec.key), tz=tz)
        if value is None and spec.required and not partial:
            raise FieldError(spec.key, "is required")
        out[spec.key] = value
    return out


def clean_config(vertical: Vertical, data: dict[str, Any]) -> dict[str, Any]:
    """A vertical's settings: known fields only, plus the home-service time windows."""
    out = clean(vertical.config_fields, data, partial=True)
    windows = data.get("time_windows")
    if isinstance(windows, list) and "time_windows" in vertical.config_defaults:
        cleaned = []
        for raw in windows[:6]:
            if not isinstance(raw, dict):
                continue
            start, end = parse_time(raw.get("start")), parse_time(raw.get("end"))
            key = re.sub(r"[^a-z0-9_]", "", str(raw.get("key") or "").lower())[:20]
            if start and end and end > start and key:
                cleaned.append({"key": key, "start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")})
        if cleaned:
            out["time_windows"] = cleaned
    return {key: value for key, value in out.items() if value is not None}


def split_record(vertical: Vertical, data: dict[str, Any], *, partial: bool = False, tz: tzinfo | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record form input → (column values, details values)."""
    values = clean(vertical.record_fields, data, partial=partial, tz=tz)
    columns = {key: value for key, value in values.items() if next(s for s in vertical.record_fields if s.key == key).column}
    details = {key: value for key, value in values.items() if key not in columns}
    extra = data.get("details")
    if isinstance(extra, dict):
        known = {spec.key for spec in vertical.record_fields}
        details.update({key: value for key, value in extra.items() if key in known and key not in columns})
    return columns, details


def split_catalog(vertical: Vertical, data: dict[str, Any], *, partial: bool = False) -> tuple[str | None, dict[str, Any]]:
    """Catalog form input → (name, data)."""
    values = clean(vertical.catalog_fields, data, partial=partial)
    name = values.pop("name", None)
    return (str(name) if name else None), {key: value for key, value in values.items() if value is not None}


__all__ = ["FieldError", "clean", "clean_config", "coerce", "split_catalog", "split_record"]
