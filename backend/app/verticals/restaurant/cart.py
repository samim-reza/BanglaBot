"""The cart: its data shape, the edits ``update_cart`` makes, and every amount (never the model's).

A cart is a JSON list kept in the ``cart`` slot; one line per item + options::

    {"id": "<catalog id>", "ref": "I3", "name": "Pepperoni Pizza", "qty": 2,
     "options": [{"group": "Size", "label": "Large", "price": 4.0}],
     "notes": "well done", "unit": 18.0, "missing": []}

``unit`` = menu price + option prices; ``missing`` = required groups not chosen yet
(the cart step asks for them before "anything else?").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.verticals.common import join_and
from app.verticals.restaurant.config import num, whole
from app.verticals.restaurant.menu import Chosen, MenuItem, Option, match_options, missing_groups

MAX_LINES = 30
MAX_QTY = 50


def make_line(item: MenuItem, qty: int, chosen: Chosen, notes: str = "") -> dict[str, Any]:
    options = [
        {"group": group.name, "label": option.label, "price": option.price}
        for group in item.groups
        for option in chosen.picks.get(group.name, [])
    ]
    parts = [part.strip() for chunk in (notes, *chosen.notes) for part in str(chunk or "").split(";")]
    note = "; ".join(dict.fromkeys(part for part in parts if part))
    return {
        "id": item.id,
        "ref": item.ref,
        "name": item.name,
        "qty": max(1, min(MAX_QTY, qty)),
        "options": options,
        "notes": note[:200],
        "unit": round(item.price + sum(o["price"] for o in options), 2),
        "missing": missing_groups(item.groups, chosen.picks),
    }


def picks_of(line: dict[str, Any], item: MenuItem) -> dict[str, list[Option]]:
    """A line's chosen options back as menu options (to merge new choices into)."""
    wanted = {(o["group"], o["label"]) for o in line.get("options") or []}
    return {g.name: [o for o in g.options if (g.name, o.label) in wanted] for g in item.groups if any(n == g.name for n, _ in wanted)}


def reprice(line: dict[str, Any], item: MenuItem, phrases: list[str], notes: str | None = None) -> dict[str, Any]:
    """The line with new option words merged in (single-choice groups take the newest pick);
    ``notes`` replaces the line's kitchen note, ``None`` keeps it."""
    chosen = match_options(item.groups, phrases, picks_of(line, item))
    base = str(line.get("notes") or "") if notes is None else notes
    return make_line(item, whole(line.get("qty"), 1), chosen, base)


def same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    key = lambda line: (line.get("id"), sorted(o["label"] for o in line.get("options") or []), line.get("notes") or "")  # noqa: E731
    return key(a) == key(b)


def add_line(cart: list[dict[str, Any]], line: dict[str, Any]) -> list[dict[str, Any]]:
    for existing in cart:
        if same(existing, line):
            existing["qty"] = min(MAX_QTY, whole(existing.get("qty"), 1) + line["qty"])
            return cart
    if len(cart) < MAX_LINES:
        cart.append(line)
    return cart


def pending_line(cart: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first line still missing a required choice."""
    return next((line for line in cart if line.get("missing")), None)


# ---- amounts -------------------------------------------------------------------------------------
def line_total(line: dict[str, Any]) -> float:
    return round(num(line.get("unit")) * whole(line.get("qty"), 1), 2)


def subtotal(cart: list[dict[str, Any]]) -> float:
    return round(sum(line_total(line) for line in cart or []), 2)


@dataclass
class Totals:
    subtotal: float
    delivery_fee: float = 0.0
    free_delivery: bool = False
    tax: float = 0.0
    tax_rate: float = 0.0
    total: float = 0.0
    extras: dict[str, float] = field(default_factory=dict)


def totals(cart: list[dict[str, Any]], fulfillment: str, config: dict[str, Any]) -> Totals:
    """Subtotal + delivery fee (waived over the free-delivery threshold) + tax on the food."""
    sub = subtotal(cart)
    fee = 0.0
    free = False
    if fulfillment == "delivery":
        fee = round(max(0.0, num(config.get("delivery_fee"))), 2)
        threshold = num(config.get("free_delivery_over"))
        if fee and threshold > 0 and sub >= threshold:
            fee, free = 0.0, True
    rate = max(0.0, num(config.get("tax_rate")))
    tax = round(sub * rate / 100, 2)
    return Totals(subtotal=sub, delivery_fee=fee, free_delivery=free, tax=tax, tax_rate=rate, total=round(sub + fee + tax, 2))


def free_delivery_gap(cart: list[dict[str, Any]], config: dict[str, Any]) -> float:
    """How much more food gets free delivery (0 = already free / no threshold / no fee)."""
    threshold = num(config.get("free_delivery_over"))
    if threshold <= 0 or num(config.get("delivery_fee")) <= 0:
        return 0.0
    return round(max(0.0, threshold - subtotal(cart)), 2)


# ---- words -----------------------------------------------------------------------------------------
def describe(line: dict[str, Any]) -> str:
    labels = [o["label"] for o in line.get("options") or []]
    text = f"{whole(line.get('qty'), 1)} {line.get('name', '')}"
    return f"{text} ({', '.join(labels)})" if labels else text


def cart_phrase(cart: list[dict[str, Any]], language: str) -> str:
    return join_and([describe(line) for line in cart or []], language)


def items_summary(cart: list[dict[str, Any]]) -> str:
    """One line for the records table: ``2× Pepperoni Pizza (Large), 1× Garlic Bread``."""
    parts = []
    for line in cart or []:
        labels = [o["label"] for o in line.get("options") or []]
        text = f"{whole(line.get('qty'), 1)}× {line.get('name', '')}" + (f" ({', '.join(labels)})" if labels else "")
        if line.get("notes"):
            text += f" — {line['notes']}"
        parts.append(text)
    return ", ".join(parts)


def record_items(cart: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cart as stored on the order (``details.items``)."""
    return [
        {
            "item_id": line.get("id"),
            "name": line.get("name"),
            "qty": whole(line.get("qty"), 1),
            "options": [{"group": o["group"], "label": o["label"], "price": o["price"]} for o in line.get("options") or []],
            "notes": line.get("notes") or "",
            "unit_price": num(line.get("unit")),
            "line_total": line_total(line),
        }
        for line in cart or []
    ]


__all__ = [
    "Totals",
    "add_line",
    "cart_phrase",
    "describe",
    "free_delivery_gap",
    "items_summary",
    "line_total",
    "make_line",
    "pending_line",
    "picks_of",
    "record_items",
    "reprice",
    "same",
    "subtotal",
    "totals",
]
