"""What a business engine (vertical) declares to the main engine and the portal.

A :class:`Vertical` bundles:

- its conversation flows, one per call direction (``inbound`` / ``outbound``);
- the vocabulary the portal shows (what a *record* is called — order,
  appointment, lead, booking — and what a *catalog item* is — doctor,
  listing, service);
- field specs for the record form, the catalog form and the vertical's
  settings, so one schema-driven UI serves every vertical;
- per-status labels (a lead's ``confirmed`` reads "Visit booked").

The admin picks the vertical when creating an account; it never changes after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.flows.base import Flow

#: Field types the portal knows how to render.
FIELD_TYPES = (
    "text", "textarea", "phone", "money", "number", "date", "time", "datetime",
    "select", "multiselect", "days", "catalog", "bool", "list",
)
#: Record columns a record field may map to (everything else lives in ``details``).
RECORD_COLUMNS = (
    "order_ref", "customer_name", "customer_phone", "address", "items_summary",
    "total_amount", "notes", "scheduled_at", "catalog_item_id",
)


def L(en: str, bn: str = "") -> dict[str, str]:
    """A label in both portal languages."""
    return {"en": en, "bn": bn or en}


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: dict[str, str]
    type: str = "text"
    required: bool = False
    #: ``(value, label)`` pairs for select / multiselect.
    options: tuple[tuple[str, dict[str, str]], ...] = ()
    help: dict[str, str] = field(default_factory=dict)
    placeholder: str = ""
    default: Any = None
    #: Shown in the records table.
    list_column: bool = False

    @property
    def column(self) -> str | None:
        return self.key if self.key in RECORD_COLUMNS else None

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "options": [{"value": value, "label": label} for value, label in self.options],
            "help": self.help,
            "placeholder": self.placeholder,
            "default": self.default,
            "list_column": self.list_column,
            "column": self.column,
        }


@dataclass(frozen=True)
class Vertical:
    key: str
    label: dict[str, str]
    description: dict[str, str]
    #: ``orders.kind`` for this vertical's records.
    record_kind: str
    record_label: dict[str, str]
    record_label_plural: dict[str, str]
    record_fields: tuple[FieldSpec, ...]
    flows: dict[str, Flow]
    catalog_kind: str = ""
    catalog_label: dict[str, str] = field(default_factory=dict)
    catalog_label_plural: dict[str, str] = field(default_factory=dict)
    catalog_fields: tuple[FieldSpec, ...] = ()
    config_fields: tuple[FieldSpec, ...] = ()
    config_defaults: dict[str, Any] = field(default_factory=dict)
    #: Status → label overrides (the generic labels are used otherwise).
    status_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    #: What an outbound call from the portal does ("Confirmation call", "Reminder call").
    outbound_label: dict[str, str] = field(default_factory=lambda: L("Call", "কল"))
    #: Records have a time (appointment, visit, service window).
    scheduled: bool = False
    #: One-line description of a record for tables and logs.
    summarize: Callable[[Any, dict[str, str]], str] | None = None

    @property
    def directions(self) -> list[str]:
        return list(self.flows)

    def flow(self, direction: str) -> Flow | None:
        return self.flows.get(direction)

    def config(self, merchant: Any) -> dict[str, Any]:
        """The merchant's vertical settings over this vertical's defaults."""
        stored = getattr(merchant, "vertical_config", None)
        merged = dict(self.config_defaults)
        if isinstance(stored, dict):
            merged.update({key: value for key, value in stored.items() if value is not None})
        return merged

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "record_kind": self.record_kind,
            "record_label": self.record_label,
            "record_label_plural": self.record_label_plural,
            "record_fields": [spec.as_json() for spec in self.record_fields],
            "catalog_kind": self.catalog_kind,
            "catalog_label": self.catalog_label,
            "catalog_label_plural": self.catalog_label_plural,
            "catalog_fields": [spec.as_json() for spec in self.catalog_fields],
            "config_fields": [spec.as_json() for spec in self.config_fields],
            "config_defaults": self.config_defaults,
            "status_labels": self.status_labels,
            "outbound_label": self.outbound_label,
            "directions": self.directions,
            "scheduled": self.scheduled,
        }


__all__ = ["FIELD_TYPES", "RECORD_COLUMNS", "FieldSpec", "L", "Vertical"]
