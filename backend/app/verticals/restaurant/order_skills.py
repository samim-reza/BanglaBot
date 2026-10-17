"""The order's other steps: pickup or delivery, the address, when, and an optional upsell."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.flows.timefmt import time_phrase
from app.skills.base import BoundSkill, Skill
from app.skills.library.choice import ChoiceSkill
from app.skills.library.lines import line
from app.verticals.base import FieldSpec, L
from app.verticals.common import closure_sentence, money, notice, when_phrase
from app.verticals.restaurant.cart import add_line, free_delivery_gap, make_line, subtotal
from app.verticals.restaurant.config import LEAD, conf, num
from app.verticals.restaurant.hours import (
    ASAP,
    can_do_asap,
    closed_on,
    earliest_ready,
    hours_phrase,
    next_opening,
    order_time_ok,
    parse_order_time,
)
from app.verticals.restaurant.menu import find_item, match_options


def _is_order(slots: dict[str, Any]) -> bool:
    return str(slots.get("intent") or "order") == "order"


def delivers(ctx: CallContext) -> bool:
    return conf(ctx).get("delivery") is not False


class FulfillmentSkill(ChoiceSkill):
    key = "fulfillment"
    slot = "fulfillment"
    toggleable = False
    label = L("Pickup or delivery")
    description = L("Pickup, or delivery when you deliver (Settings).")
    slots = (SlotSpec("fulfillment", "pickup or delivery, once the caller says.", {"type": "string", "enum": ["pickup", "delivery"]}),)
    volunteerable = frozenset({"fulfillment"})
    synonyms = {
        "pickup": ("pickup", "pick up", "pick it up", "collect", "collection", "takeaway", "take away", "carry out", "carryout", "to go"),
        "delivery": ("delivery", "deliver", "bring it"),
    }
    lines = (
        line("ask", "Is that for pickup or delivery?", label="Ask pickup or delivery", static=True),
        line("minimum", "Delivery needs a minimum order of {minimum}, and your order is {subtotal} so far. Would you like to add something, or make it pickup?", label="Below the delivery minimum", variables=("minimum", "subtotal")),
        line("pickup_only", "Sorry, we don't deliver — orders are for pickup.", label="No delivery", static=True),
    )
    goal = "Pickup or delivery?"

    def _below_minimum(self, slots: dict[str, Any], ctx: CallContext) -> bool:
        minimum = num(conf(ctx).get("minimum_order"))
        return slots.get("fulfillment") == "delivery" and minimum > 0 and subtotal(slots.get("cart") or []) < minimum

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        if _is_order(slots) and not delivers(ctx):
            slots["fulfillment"] = "pickup"

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if not slots.get("fulfillment") or self._below_minimum(slots, ctx):
            return "fulfillment"
        return None

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        if fields.get("fulfillment") == "delivery" and not delivers(ctx):
            fields.pop("fulfillment")
            fields[LEAD] = b.text("pickup_only", language)
        return fields, None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if self._below_minimum(slots, ctx):
            return b.text("minimum", language, minimum=money(conf(ctx).get("minimum_order"), ctx, language), subtotal=money(subtotal(slots.get("cart") or []), ctx, language))
        return b.text("ask", language)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask", language), b.text("pickup_only", language)]


class AddressSkill(Skill):
    key = "address"
    toggleable = False
    label = L("Delivery address")
    slots = (SlotSpec("address", "Delivery address as the caller said it (street and number, apartment, area)."),)
    long_answer = frozenset({"address"})
    volunteerable = frozenset({"address"})
    lines = (line("address", "What's the delivery address?", label="Ask for the address", static=True),)
    goal = "Get the full delivery address."

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return slots.get("fulfillment") == "delivery"

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        text = " ".join(str(fields.get("address") or "").split())[:300]
        if len(text) < 4:
            fields.pop("address", None)
        else:
            fields["address"] = text
        return fields, None

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("address", language)]


#: Set (once) when a requested ready time was moved to the earliest the kitchen can do.
READY_MOVED = "_ready_moved"


class OrderTimeSkill(Skill):
    key = "order_time"
    label = L("When")
    description = L("As soon as possible, or a later time within your hours.")
    options = (FieldSpec("ask", L("Ask when they want it (off = as soon as possible)"), "bool", default=True),)
    defaults = {"ask": True}
    slots = (SlotSpec("order_time", "asap, or when they want it: HH:MM today, or YYYY-MM-DD HH:MM."),)
    volunteerable = frozenset({"order_time"})
    lines = (
        line("ask", "Would you like it as soon as possible, or for a later time?", label="Ask when", static=True),
        line("closed", "We're closed right now — we open {next}. What time would you like it?", label="Closed now", variables=("next",)),
        line("outside", "We're open {hours}. What time would you like it?", label="Outside hours", variables=("hours",)),
        line("closed_date", "{closure} What time would you like it?", label="Closed that day", variables=("closure",)),
    )
    asap_words = ("asap", "as soon as", "right away", "right now", "now please", "soonest", "quickly")
    goal = "As soon as possible, or a later time?"

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        if not b.opt("ask", True) and not slots.get("order_time") and _is_order(slots) and can_do_asap(slots, ctx):
            slots["order_time"] = ASAP

    def _closure_line(self, b: BoundSkill, ctx: CallContext, day: date, language: str) -> str | None:
        """"We're closed on Thursday, November 26 for Thanksgiving — the next open day is …" when ``day`` is a closure."""
        closure = closed_on(ctx, day)
        if closure is None:
            return None
        assert ctx.now is not None
        opens = next_opening(ctx, datetime.combine(day + timedelta(days=1), dtime(0, 0), tzinfo=ctx.now.tzinfo))
        return b.text("closed_date", language, closure=closure_sentence(ctx, closure, next_day=opens.date() if opens else None))

    def _closed_line(self, b: BoundSkill, ctx: CallContext, language: str) -> str:
        assert ctx.now is not None
        closure = self._closure_line(b, ctx, ctx.today, language)
        if closure:
            return closure
        opens = next_opening(ctx, ctx.now)
        if opens is None or opens <= ctx.now:
            return b.text("outside", language, hours=hours_phrase(ctx, language))
        return b.text("closed", language, next=when_phrase(opens, ctx, language))

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        parsed = parse_order_time(fields.get("order_time"), ctx)
        if parsed == ASAP:
            if can_do_asap({**slots, **fields}, ctx):
                fields["order_time"] = ASAP
                return fields, None
            fields.pop("order_time")
            return fields, Instruction("order_time", self._closed_line(b, ctx, language), verbatim=True)
        closure = self._closure_line(b, ctx, parsed.date(), language) if isinstance(parsed, datetime) else None
        if closure:
            fields.pop("order_time", None)
            return fields, Instruction("order_time", closure, verbatim=True)
        if parsed is None or not order_time_ok(parsed, ctx):  # type: ignore[arg-type]
            fields.pop("order_time", None)
            return fields, Instruction("order_time", b.text("outside", language, hours=hours_phrase(ctx, language)), verbatim=True)
        # Not before the kitchen can have it ready ("11 AM" when it opens at 11 and needs 20 minutes → 11:20).
        earliest = earliest_ready(parsed, {**slots, **fields}, ctx)  # type: ignore[arg-type]
        if parsed < earliest:  # type: ignore[operator]
            parsed = earliest
            fields[READY_MOVED] = time_phrase(earliest.timetz(), language)
        fields["order_time"] = parsed.isoformat()  # type: ignore[union-attr]
        return fields, None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        moved = slots.pop(READY_MOVED, None)
        if moved:
            notice(slots, "ready_moved", time=moved)  # said before the next line

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("ask", language) if can_do_asap(slots, ctx) else self._closed_line(b, ctx, language)

    def fast_fields(self, b: BoundSkill, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        lowered = " ".join(str(text or "").lower().split())
        if stage == "order_time" and len(lowered.split()) <= 6 and any(word in lowered for word in self.asap_words) and can_do_asap(slots, ctx):
            return {"order_time": ASAP}
        return None

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask", language)]


class UpsellSkill(Skill):
    """One suggestion, at most once: the free-delivery gap or an item the owner picks."""

    key = "upsell"
    kind = "gate"
    label = L("Suggest one more thing")
    description = L("Once per order: a free-delivery nudge or an item you choose.")
    default_enabled = False
    options = (
        FieldSpec("mode", L("Suggest"), "select", options=(("free_delivery", L("Free delivery nudge")), ("item", L("An item"))), default="free_delivery"),
        FieldSpec("item", L("Item to suggest"), placeholder="Garlic Bread"),
        FieldSpec("max_gap", L("Only when this close to free delivery"), "money", default=10),
    )
    defaults = {"mode": "free_delivery", "max_gap": 10}
    slots = (SlotSpec("upsell_ok", "Answer to the one suggestion: true = yes, false = no.", {"type": "boolean"}),)
    yes_no = {"upsell": "upsell_ok"}
    stage_slots = {"upsell": ("upsell_ok",)}
    lines = (
        line("gap", "You're {gap} away from free delivery. Would you like to add anything?", label="Free delivery nudge", variables=("gap",)),
        line("item", "Would you like to add {item} for {price}?", label="Item suggestion", variables=("item", "price")),
    )
    goal = "The system made one suggestion: save upsell_ok, or call update_cart if they add something."

    def _item(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext):  # noqa: ANN202
        found = find_item(ctx, b.opt("item", ""))
        item = found.best if found.status == "ok" else None
        if item is None or not item.available or any(line.get("id") == item.id for line in slots.get("cart") or []):
            return None
        return item

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("upsell",)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if slots.get("_upsell_asked") or slots.get("upsell_ok") is not None:
            return None
        if b.opt("mode") == "item":
            return "upsell" if self._item(b, slots, ctx) else None
        gap = free_delivery_gap(slots.get("cart") or [], conf(ctx))
        wanted = slots.get("fulfillment") == "delivery" and 0 < gap <= num(b.opt("max_gap", 10))
        return "upsell" if wanted else None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        slots["_upsell_asked"] = True
        if b.opt("mode") == "item":
            item = self._item(b, slots, ctx)
            return b.text("item", language, item=item.name if item else "", price=money(item.price if item else 0, ctx, language))
        gap = free_delivery_gap(slots.get("cart") or [], conf(ctx))
        return b.text("gap", language, gap=money(gap, ctx, language))

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        if fields.get("upsell_ok") is not True:
            return fields, None
        if b.opt("mode") == "item":
            item = self._item(b, slots, ctx)
            if item is not None:
                cart = [dict(line) for line in slots.get("cart") or []]
                fields["cart"] = add_line(cart, make_line(item, 1, match_options(item.groups, [])))
        else:
            fields["more_items"] = True  # back to "What else would you like?"
        return fields, None


__all__ = ["AddressSkill", "FulfillmentSkill", "OrderTimeSkill", "UpsellSkill", "delivers"]
