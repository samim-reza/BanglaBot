"""The menu: catalog items with price, modifier groups, allergens, aliases and availability.

Modifiers are written by the owner in one line of plain text::

    Size*: Small | Medium +2 | Large +4; Extras+: Cheese +1 | Bacon +2; Crust: Thin | Thick

``;`` (or a new line) separates groups, ``|`` options; a trailing number is the
option's extra price. ``*`` after the group name = the caller must choose one;
``+`` = several may be chosen; otherwise at most one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.flows.context import CallContext, CatalogEntry
from app.verticals.restaurant.config import KIND_MENU_ITEM, num
from app.verticals.restaurant.match import best_match, norm, score

MAX_GROUPS = 8
MAX_OPTIONS = 16
_PRICE = re.compile(r"^(.*?\S)\s+\(?([+-]?)\s*\$?(\d+(?:[.,]\d{1,2})?)\)?$")
#: Words that make a modifier a removal / kitchen note rather than a priced option.
_NEGATION = ("no ", "without ", "hold ", "less ", "light ", "not ", "extra hot", "on the side")


@dataclass(frozen=True)
class Option:
    label: str
    price: float = 0.0


@dataclass(frozen=True)
class Group:
    name: str
    options: tuple[Option, ...]
    required: bool = False
    multi: bool = False


def _option(text: str) -> Option | None:
    text = " ".join(str(text or "").split())
    if not text:
        return None
    match = _PRICE.match(text)
    if match:
        price = num(match.group(3).replace(",", "."))
        return Option(match.group(1).strip(), -price if match.group(2) == "-" else price)
    return Option(text)


@lru_cache(maxsize=1024)
def parse_modifiers(text: str) -> tuple[Group, ...]:
    """``"Size*: Small | Large +4; Extras+: Cheese +1"`` → groups (unparseable parts are ignored)."""
    groups: list[Group] = []
    for chunk in re.split(r"[;\n]+", str(text or "")):
        if ":" not in chunk:
            continue
        head, body = chunk.split(":", 1)
        name = head.strip()
        flags = ""
        while name and name[-1] in "*+":
            flags += name[-1]
            name = name[:-1].strip()
        options = tuple(opt for opt in (_option(part) for part in body.split("|")) if opt is not None)[:MAX_OPTIONS]
        if name and options:
            groups.append(Group(name[:40], options, required="*" in flags, multi="+" in flags))
    return tuple(groups[:MAX_GROUPS])


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[\n,;]+", value)
    return [" ".join(str(v).split()) for v in (value or []) if str(v).strip()]


@dataclass(frozen=True)
class MenuItem:
    entry: CatalogEntry

    @property
    def id(self) -> str:
        return self.entry.id

    @property
    def ref(self) -> str:
        return self.entry.ref

    @property
    def name(self) -> str:
        return self.entry.name

    @property
    def price(self) -> float:
        return round(num(self.entry.get("price")), 2)

    @property
    def category(self) -> str:
        return str(self.entry.get("category", "") or "")

    @property
    def available(self) -> bool:
        value = self.entry.data.get("available", True)
        return value is not False and str(value).lower() not in ("false", "0", "no")

    @property
    def aliases(self) -> list[str]:
        return _text_list(self.entry.get("aliases"))

    @property
    def allergens(self) -> list[str]:
        return _text_list(self.entry.get("allergens"))

    @property
    def groups(self) -> tuple[Group, ...]:
        raw = self.entry.get("modifiers")
        return parse_modifiers(raw if isinstance(raw, str) else "; ".join(_text_list(raw)))

    def names(self) -> list[str]:
        return [self.name, self.ref, *self.aliases]


def menu_items(ctx: CallContext) -> list[MenuItem]:
    return [MenuItem(entry) for entry in ctx.items(KIND_MENU_ITEM)]


def item_by_id(ctx: CallContext, item_id: Any) -> MenuItem | None:
    entry = ctx.item_by_id(item_id)
    return MenuItem(entry) if entry is not None and entry.kind == KIND_MENU_ITEM else None


def find_item(ctx: CallContext, query: Any):  # noqa: ANN201 — Found[MenuItem]
    return best_match(str(query or ""), ((item, item.names()) for item in menu_items(ctx)))


# ---- options -----------------------------------------------------------------------------------
@dataclass
class Chosen:
    #: group name → chosen options (in order).
    picks: dict[str, list[Option]]
    #: Words that matched no option (kept as a kitchen note, never priced).
    notes: list[str]


def match_options(groups: tuple[Group, ...], phrases: list[str], picks: dict[str, list[Option]] | None = None) -> Chosen:
    """Resolve the caller's modifier words against an item's groups; one pick per single-choice group."""
    chosen = {name: list(options) for name, options in (picks or {}).items()}
    notes: list[str] = []
    for phrase in phrases:
        text = " ".join(str(phrase or "").split())
        if not text:
            continue
        lowered = f"{text.lower()} "
        if lowered.startswith(_NEGATION) or any(f" {word}" in f" {lowered}" for word in _NEGATION[:4]):
            notes.append(text)
            continue
        hit = best_option(groups, text)
        if hit is None:
            notes.append(text)
            continue
        group, option = hit
        current = chosen.setdefault(group.name, [])
        if group.multi:
            if option not in current:
                current.append(option)
        else:
            chosen[group.name] = [option]
    return Chosen({name: opts for name, opts in chosen.items() if opts}, notes)


def best_option(groups: tuple[Group, ...], text: str) -> tuple[Group, Option] | None:
    wanted = norm(text)
    best: tuple[int, Group, Option] | None = None
    for group in groups:
        for option in group.options:
            value = score(wanted, norm(option.label))
            if value >= 65 and (best is None or value > best[0]):
                best = (value, group, option)
    return (best[1], best[2]) if best else None


def missing_groups(groups: tuple[Group, ...], picks: dict[str, list[Option]]) -> list[str]:
    return [group.name for group in groups if group.required and not picks.get(group.name)]


# ---- facts for the model -------------------------------------------------------------------------
def _price_text(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") if value else "0"


def options_text(groups: tuple[Group, ...], *, detail: bool) -> str:
    def label(option: Option) -> str:
        return option.label + (f" +{_price_text(option.price)}" if detail and option.price else "")

    return "; ".join(f"{g.name}{'*' if g.required else ''}: " + "/".join(label(o) for o in g.options) for g in groups)


def item_fact(item: MenuItem, *, detail: bool, options: bool = True) -> str:
    parts = [f"{item.name} {_price_text(item.price)}"]
    if item.groups and options:
        parts.append(f"({options_text(item.groups, detail=detail)})")
    if item.allergens:
        parts.append(f"[allergens: {', '.join(item.allergens)}]")
    if detail and item.entry.get("description"):
        parts.append(f"— {item.entry.get('description')}")
    if not item.available:
        parts.append("(not available today)")
    return " ".join(parts)


def menu_facts(ctx: CallContext, *, detail: bool = False) -> list[str]:
    """The menu by category, compact (``detail`` adds option prices and descriptions).

    Options every item of a category shares (all pizzas: sizes, crusts) are listed once."""
    items = menu_items(ctx)
    if not items:
        return ["Menu: (not added yet — take a message for the team)."]
    lines = [f"Menu ({ctx.currency}; * = must choose; allergens only as listed):"]
    by_category: dict[str, list[MenuItem]] = {}
    for item in items:
        by_category.setdefault(item.category or "Other", []).append(item)
    for category, group in by_category.items():
        shared = {item.groups for item in group}
        hoist = len(group) > 1 and len(shared) == 1 and bool(group[0].groups)
        head = f"- {category} (options for all: {options_text(group[0].groups, detail=detail)})" if hoist else f"- {category}"
        lines.append(f"{head}: " + "; ".join(item_fact(item, detail=detail, options=not hoist) for item in group))
    return lines


__all__ = [
    "Chosen",
    "Group",
    "MenuItem",
    "Option",
    "best_option",
    "find_item",
    "item_by_id",
    "item_fact",
    "match_options",
    "menu_facts",
    "menu_items",
    "missing_groups",
    "options_text",
    "parse_modifiers",
]
