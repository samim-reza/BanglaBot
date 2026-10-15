"""Apply ``update_cart`` edits: add / remove / set_qty / replace, matched against the menu (and the cart).

Pure over (cart, edits, context): returns the new cart and a :class:`Report` of
what happened, which the cart skill turns into the next spoken line. Nothing is
priced from the model — items, options and prices all come from the menu.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from app.flows.context import CallContext
from app.verticals.restaurant.cart import add_line, make_line, reprice, same
from app.verticals.restaurant.config import whole
from app.verticals.restaurant.match import best_match
from app.verticals.restaurant.menu import MenuItem, find_item, item_by_id, match_options

ACTIONS = ("add", "remove", "set_qty", "replace")
MAX_EDITS = 12


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    not_in_order: list[str] = field(default_factory=list)
    #: Names to choose between (the first unclear item of the turn).
    choose: list[str] = field(default_factory=list)
    #: A near miss to confirm: ``{"item_id", "name", "qty", "modifiers", "notes"}``.
    suggest: dict[str, Any] | None = None

    @property
    def edited(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def as_json(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if value}


def _phrases(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [" ".join(str(v).split()) for v in (value or []) if str(v).strip()][:8]


def edits_from(args: dict[str, Any]) -> list[dict[str, Any]]:
    """The model's ``items`` (tolerating a single object or a bare string)."""
    raw = args.get("items")
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, str):
        raw = [{"item": raw}]
    edits = [entry if isinstance(entry, dict) else {"item": str(entry)} for entry in (raw or [])]
    unique: dict[tuple, dict[str, Any]] = {}
    for entry in edits:
        if not str(entry.get("item") or "").strip():
            continue
        action = str(entry.get("action") or "add").lower()
        key = (str(entry["item"]).strip().lower(), action, tuple(p.lower() for p in _phrases(entry.get("modifiers"))), str(entry.get("notes") or ""), str(entry.get("replace_with") or ""))
        if action == "add" and key in unique:
            # The same item listed twice in one call is a repeat, not a second order: keep the larger quantity.
            unique[key]["qty"] = max(whole(unique[key].get("qty"), 1), whole(entry.get("qty"), 1))
            continue
        unique[key if action == "add" else (*key, len(unique))] = dict(entry)
    return list(unique.values())[:MAX_EDITS]


def add_item(cart: list[dict[str, Any]], item: MenuItem, qty: int, phrases: list[str], notes: str, report: Report) -> None:
    if not item.available:
        report.unavailable.append(item.name)
        return
    waiting = next((line for line in cart if line.get("id") == item.id and line.get("missing")), None)
    if waiting is not None and phrases:
        # "Large" for the pizza still waiting for a size fills that line instead of adding another.
        index = cart.index(waiting)
        cart[index] = reprice(waiting, item, phrases, notes or None)
        report.changed.append(item.name)
        return
    add_line(cart, make_line(item, qty, match_options(item.groups, phrases), notes))
    report.added.append(item.name)


def _in_cart(cart: list[dict[str, Any]], query: str, ctx: CallContext, report: Report) -> int | None:
    """Index of the cart line ``query`` means (remove / set_qty / replace), or None (reported)."""
    found = best_match(query, ((index, [line.get("name", ""), line.get("ref", "")]) for index, line in enumerate(cart)))
    if found.status in ("ok", "suggest") and found.best is not None:
        return found.best
    if found.status == "choose":
        names = list(dict.fromkeys(cart[index].get("name", "") for index in found.choices))
        if len(names) == 1:
            return found.choices[-1]
        report.choose = report.choose or names
        return None
    menu = find_item(ctx, query)
    report.not_in_order.append(menu.best.name if menu.status == "ok" and menu.best else query)
    return None


def _edit(cart: list[dict[str, Any]], edit: dict[str, Any], ctx: CallContext, report: Report) -> None:
    query = " ".join(str(edit.get("item") or "").split())[:80]
    action = str(edit.get("action") or "add").lower()
    action = action if action in ACTIONS else "add"
    phrases = _phrases(edit.get("modifiers"))
    notes = " ".join(str(edit.get("notes") or "").split())[:160]
    qty = whole(edit.get("qty"), 0)
    if action == "add":
        found = find_item(ctx, query)
        if found.status == "ok" and found.best is not None:
            add_item(cart, found.best, qty or 1, phrases, notes, report)
        elif found.status == "suggest" and found.best is not None and not found.best.available:
            report.not_found.append(query)
        elif found.status == "suggest" and found.best is not None and report.suggest is None:
            report.suggest = {"item_id": found.best.id, "name": found.best.name, "qty": qty or 1, "modifiers": phrases, "notes": notes}
        elif found.status == "choose":
            report.choose = report.choose or [item.name for item in found.choices]
        else:
            report.not_found.append(query)
        return
    index = _in_cart(cart, query, ctx, report)
    if index is None:
        return
    line = cart[index]
    name = str(line.get("name", ""))
    item = item_by_id(ctx, line.get("id"))
    if action == "remove":
        if 0 < qty < whole(line.get("qty"), 1):
            line["qty"] = whole(line.get("qty"), 1) - qty
            report.changed.append(name)
        else:
            cart.pop(index)
            report.removed.append(name)
        return
    if action == "set_qty":
        if qty <= 0:
            cart.pop(index)
            report.removed.append(name)
        else:
            line["qty"] = min(50, qty)
            report.changed.append(name)
        return
    swap = " ".join(str(edit.get("replace_with") or "").split())
    if swap:
        found = find_item(ctx, swap)
        if found.status != "ok" or found.best is None:
            report.not_found.append(swap)
            return
        if not found.best.available:
            report.unavailable.append(found.best.name)
            return
        cart[index] = make_line(found.best, qty or whole(line.get("qty"), 1), match_options(found.best.groups, phrases), notes)
        report.changed.append(found.best.name)
        return
    if item is None:
        return
    updated = reprice(line, item, phrases, notes or None)
    if qty > 0:
        updated["qty"] = min(50, qty)
    cart[index] = updated
    report.changed.append(name)


def apply_edits(cart: list[dict[str, Any]] | None, edits: list[dict[str, Any]], ctx: CallContext) -> tuple[list[dict[str, Any]], Report]:
    new = copy.deepcopy(list(cart or []))
    report = Report()
    for edit in edits:
        _edit(new, edit, ctx, report)
    # Identical lines created by edits (e.g. a size filled in) merge into one.
    merged: list[dict[str, Any]] = []
    for line in new:
        twin = next((other for other in merged if same(other, line)), None)
        if twin is not None:
            twin["qty"] = min(50, whole(twin.get("qty"), 1) + whole(line.get("qty"), 1))
        else:
            merged.append(line)
    return merged, report


def accept_suggestion(cart: list[dict[str, Any]] | None, pending: dict[str, Any], ctx: CallContext) -> tuple[list[dict[str, Any]], Report]:
    """The caller said yes to "did you mean …?": add that item as they asked for it."""
    new = copy.deepcopy(list(cart or []))
    report = Report()
    item = item_by_id(ctx, pending.get("item_id"))
    if item is not None:
        add_item(new, item, whole(pending.get("qty"), 1) or 1, _phrases(pending.get("modifiers")), str(pending.get("notes") or ""), report)
    return new, report


__all__ = ["ACTIONS", "Report", "accept_suggestion", "add_item", "apply_edits", "edits_from"]
