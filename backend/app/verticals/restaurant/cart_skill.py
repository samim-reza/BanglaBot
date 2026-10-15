"""Taking the order: the ``update_cart`` tool, "did you mean …?", required choices, "anything else?".

Stages (asked in this order while the cart skill is active):

    cart_pick  — "Did you mean the Margherita Pizza?"         (yes/no → ``pick_ok``)
    cart       — "What would you like to order?" / a required choice / "Which one: A or B?"
    more_items — "You have 2 Pepperoni Pizza (Large). Anything else?"  (yes/no → ``more_items``)

The skill sits in the order branch AND in the blueprint's globals, so a caller can
name food before any intent was saved ("two large pepperonis for delivery") or
change the order at any later step; ``applies`` keeps the tool out of the other
branches (reservation, status, message).
"""

from __future__ import annotations

import re

import copy
from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.common import join_and, join_or
from app.verticals.restaurant.cart import cart_phrase, make_line, pending_line, picks_of, subtotal
from app.verticals.restaurant.cart_edit import Report, accept_suggestion, apply_edits, edits_from
from app.verticals.restaurant.config import conf
from app.verticals.restaurant.menu import Chosen, best_option, item_by_id, menu_facts
from app.verticals.restaurant.match import norm

TOOL = "update_cart"
#: Order details that, given at "anything else?", mean the caller has finished choosing items.
MOVING_ON = frozenset({"fulfillment", "address", "customer_name", "order_time", "payment_method", "phone"})
ASK = "_cart_ask"
PENDING = "_cart_pending"
DONE_WORDS = (
    "that's it", "thats it", "that is it", "that's all", "thats all", "that is all", "that'll be all", "that will be all",
    "nothing else", "no thanks", "no thank you", "i'm good", "im good", "i'm done", "all good", "just that", "nope",
    "আর কিছু না", "আর কিছু লাগবে না", "আর না", "এতটুকুই", "এটুকুই", "ব্যস", "বাস",
)

UPDATE_CART = {
    "type": "function",
    "function": {
        "name": TOOL,
        "description": "Add, remove or change menu items in the order — every item of the turn in one call. The system finds and prices them.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string", "description": "The dish or drink as the caller said it."},
                            "qty": {"type": "integer", "description": "How many (add) or the new quantity (set_qty)."},
                            "modifiers": {"type": "array", "items": {"type": "string"}, "description": "Only options the caller said, in their words: size, extras, 'no onions'."},
                            "notes": {"type": "string", "description": "Other kitchen instructions."},
                            "action": {"type": "string", "enum": ["add", "remove", "set_qty", "replace"], "description": "add (default); replace = change the options of an item already ordered."},
                            "replace_with": {"type": "string", "description": "replace only: the new dish when swapping one for another."},
                        },
                        "required": ["item", "qty"],
                    },
                },
                "fulfillment": {"type": "string", "enum": ["pickup", "delivery"], "description": "Only if the caller said pickup or delivery."},
                "done": {"type": "boolean", "description": "true if they also said that's all / nothing else."},
                "customer_name": {"type": "string", "description": "Only if they said their name in this turn."},
                "address": {"type": "string", "description": "Delivery address, only if they said it in this turn."},
                "phone": {"type": "string", "description": "Only if they said a phone number in this turn."},
                "order_time": {"type": "string", "description": "asap, or HH:MM (24 h) if they asked for a later time."},
                "reply": {"type": "string", "description": "Optional one-sentence answer to a question they asked."},
            },
            "required": ["items"],
        },
    },
}


def _said(phrase: str, heard: set[str]) -> bool:
    """A modifier counts only if one of its words (or a 4-letter stem) is in the caller's words."""
    words = [w for w in re.findall(r"[a-z]+", phrase.lower().split(":")[-1]) if len(w) >= 3]
    return any(w in heard or any(h.startswith(w[:4]) for h in heard) for w in words)


def heard_modifiers(edit: dict[str, Any], caller_text: str) -> dict[str, Any]:
    """Small models add plausible extras ("extra cheese") nobody asked for: drop modifiers the caller didn't say."""
    if not caller_text or not edit.get("modifiers"):
        return edit
    heard = set(re.findall(r"[a-z]+", caller_text.lower()))
    mods = edit["modifiers"] if isinstance(edit["modifiers"], list) else [edit["modifiers"]]
    return {**edit, "modifiers": [m for m in mods if _said(str(m), heard)]}

class CartSkill(Skill):
    key = "cart"
    toggleable = False
    label = L2("Order items", "অর্ডারের আইটেম")
    description = L2("Takes the order from your menu and prices it.", "মেনু থেকে অর্ডার নেয় ও দাম হিসাব করে।")
    slots = (
        SlotSpec("more_items", "After 'Anything else?': true = they want more, false = that's all.", {"type": "boolean"}),
        SlotSpec("pick_ok", "Answer to 'Did you mean …?': true = yes, false = no.", {"type": "boolean"}),
        SlotSpec("item_option", "The option they picked when asked (e.g. the size)."),
    )
    yes_no = {"cart_pick": "pick_ok", "more_items": "more_items"}
    stage_slots = {"cart": (), "cart_pick": ("pick_ok",), "more_items": ("more_items",)}
    long_answer = frozenset({"cart"})
    passive = frozenset({ASK, PENDING, "pick_ok", "item_option"})
    lines = (
        line("ask_order", "What would you like to order?", "কী অর্ডার করতে চান?", label="Ask for the order", static=True),
        line("ask_more", "What else would you like?", "আর কী নেবেন?", label="Ask for more", static=True),
        line("anything_else", "You have {items}. Anything else?", "আপনার অর্ডারে আছে {items}। আর কিছু লাগবে?", label="Anything else?", variables=("items",)),
        line("ask_option", "Which {group} would you like for the {item}: {options}?", "{item} এর জন্য কোন {group} নেবেন: {options}?", label="Required choice", variables=("group", "item", "options")),
        line("did_you_mean", "Did you mean the {item}?", "আপনি কি {item} বলছেন?", label="Did you mean", variables=("item",)),
        line("choose", "Which one would you like: {options}?", "কোনটা নেবেন: {options}?", label="Several match", variables=("options",)),
        line("not_found", "Sorry, we don't have {item}.", "দুঃখিত, আমাদের {item} নেই।", label="Not on the menu", variables=("item",)),
        line("unavailable", "Sorry, the {item} isn't available today.", "দুঃখিত, আজ {item} পাওয়া যাচ্ছে না।", label="Not available", variables=("item",)),
        line("not_in_order", "There's no {item} in your order.", "আপনার অর্ডারে {item} নেই।", label="Not in the order", variables=("item",)),
        line("added", "Got it, I've added {items}.", "ঠিক আছে, {items} যোগ করেছি।", label="Added later", variables=("items",)),
        line("removed", "I've removed {items}.", "{items} বাদ দিয়েছি।", label="Removed later", variables=("items",)),
        line("changed", "Done, I've updated your order.", "ঠিক আছে, অর্ডার আপডেট করেছি।", label="Changed later", static=True),
    )
    goal = "Take the order: call update_cart with every item they name."

    # ---- where we are -----------------------------------------------------------------------------
    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return str(slots.get("intent") or "order") == "order"

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("cart", "cart_pick", "more_items")

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        cart = slots.get("cart") or []
        if slots.get(PENDING):
            return "cart_pick"
        if not cart or slots.get(ASK) or pending_line(cart) or slots.get("more_items") is True:
            return "cart"
        if slots.get("more_items") is None:
            return "more_items"
        return None

    def _option_question(self, b: BoundSkill, cart: list[dict[str, Any]], ctx: CallContext, language: str) -> str:
        waiting = pending_line(cart)
        item = item_by_id(ctx, waiting.get("id")) if waiting else None
        group = next((g for g in item.groups if g.name == waiting["missing"][0]), None) if item and waiting else None
        if group is None:
            return ""
        return b.text("ask_option", language, group=group.name.lower(), item=item.name, options=join_or([o.label for o in group.options], language))

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        cart = slots.get("cart") or []
        if stage == "cart_pick":
            return b.text("did_you_mean", language, item=(slots.get(PENDING) or {}).get("name", ""))
        if stage == "more_items":
            return b.text("anything_else", language, items=cart_phrase(cart, language))
        if slots.get(ASK):
            return str(slots[ASK])
        question = self._option_question(b, cart, ctx, language)
        if question:
            return question
        return b.text("ask_more" if cart else "ask_order", language)

    def brief(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext) -> str:
        cart = slots.get("cart") or []
        if stage == "cart_pick":
            return "The system asked if they meant the item it named: save pick_ok (or call update_cart with what they want instead)."
        if stage == "more_items":
            return "Anything else? Save more_items=false when they're done; for more items call update_cart."
        if pending_line(cart):
            return "The system asked them to choose an option for an item: save their choice as item_option."
        if slots.get(ASK):
            return "The system asked which item they meant: call update_cart with the one they choose."
        return self.goal

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return menu_facts(ctx)

    def fast_fields(self, b: BoundSkill, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        lowered = f" {' '.join(str(text or '').lower().replace('’', chr(39)).split()).strip(' .!,')} "
        if stage == "more_items" and len(lowered.split()) <= 6 and any(f" {word} " in lowered for word in DONE_WORDS):
            return {"more_items": False}
        waiting = pending_line(slots.get("cart") or [])
        if stage == "cart" and waiting and len(lowered.split()) <= 4:
            item = item_by_id(ctx, waiting.get("id"))
            group = next((g for g in item.groups if g.name == waiting["missing"][0]), None) if item else None
            hit = best_option((group,), text) if group else None
            if hit is not None and norm(hit[1].label) in norm(text):
                return {"item_option": hit[1].label}
        return None

    # ---- saving ------------------------------------------------------------------------------------
    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        cart = slots.get("cart") or []
        if "pick_ok" in fields:
            pending = slots.get(PENDING)
            if fields["pick_ok"] is True and pending:
                fields["cart"], _ = accept_suggestion(fields.get("cart", cart), pending, ctx)
                if slots.get("more_items") is True:
                    fields["more_items"] = None
            fields[PENDING] = None
        if "item_option" in fields:
            current = fields.get("cart", cart)
            waiting = pending_line(current)
            item = item_by_id(ctx, waiting.get("id")) if waiting else None
            group = next((g for g in item.groups if g.name == waiting["missing"][0]), None) if item and waiting else None
            if group is None:
                fields.pop("item_option")
                return fields, None
            hit = best_option((group,), str(fields["item_option"]))
            if hit is None:
                fields.pop("item_option")
                return fields, Instruction("cart", self._option_question(b, current, ctx, language), verbatim=True)
            picks = picks_of(waiting, item)
            picks[group.name] = [hit[1]]
            updated = copy.deepcopy(list(current))
            updated[updated.index(waiting)] = make_line(item, int(waiting.get("qty") or 1), Chosen(picks, []), str(waiting.get("notes") or ""))
            fields["cart"] = updated
            fields["item_option"] = hit[1].label
        return fields, None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if ASK not in saved:
            slots.pop(ASK, None)
        if PENDING not in saved and "pick_ok" not in saved:
            slots.pop(PENDING, None)
        if slots.get("cart") and slots.get("more_items") is None and "cart" not in saved and set(saved) & MOVING_ON:
            # Answering "anything else?" with the address or a name means that's all.
            slots["more_items"] = False

    # ---- the tool ------------------------------------------------------------------------------------
    def tools(self, b: BoundSkill) -> list[dict[str, Any]]:
        return [UPDATE_CART]

    def run_tool(
        self, b: BoundSkill, name: str, args: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str, *, caller_text: str = ""
    ) -> dict[str, Any]:
        if name != TOOL:
            return {"ok": False, "reason": "unknown_tool"}
        edits = [heard_modifiers(edit, caller_text) for edit in edits_from(args)]
        fulfillment = str(args.get("fulfillment") or "").strip().lower()
        if not edits and fulfillment not in ("pickup", "delivery"):
            return {"ok": False, "reason": "no_items"}
        cart, report = apply_edits(slots.get("cart"), edits, ctx)
        updates: dict[str, Any] = {ASK: None, PENDING: report.suggest}
        if report.edited:
            updates["cart"] = cart
            if slots.get("more_items") is True:
                updates["more_items"] = None
        if args.get("done") is True and cart and not (report.suggest or report.choose):
            updates["more_items"] = False  # "… and a garlic bread, that's it"
        if report.choose:
            updates[ASK] = b.text("choose", language, options=join_or(report.choose, language))
        if not slots.get("intent"):
            updates["intent"] = "order"
        if fulfillment == "pickup" or (fulfillment == "delivery" and conf(ctx).get("delivery") is not False):
            updates["fulfillment"] = fulfillment
        # Details said in the same breath ("… for delivery, I'm John at 42 Elm St") go through the
        # normal validated save path, so they aren't lost to the one-tool-per-turn limit.
        save = {key: args[key] for key in ("customer_name", "address", "phone", "order_time") if str(args.get(key) or "").strip()}
        return {
            "ok": True,
            "updates": updates,
            "save": save,
            "say": self.report_line(b, report, slots, language),
            "result": report.as_json(),
            "order_now": cart_phrase(cart, "en") or "(empty)",
            "subtotal": subtotal(cart),
        }

    def report_line(self, b: BoundSkill, report: Report, slots: dict[str, Any], language: str) -> str:
        parts = [b.text("not_found", language, item=name) for name in report.not_found[:2]]
        parts += [b.text("unavailable", language, item=name) for name in report.unavailable[:2]]
        parts += [b.text("not_in_order", language, item=name) for name in report.not_in_order[:2]]
        if report.edited and slots.get("more_items") is False:
            # Past "anything else?": confirm the change before the step's own question.
            if report.added and not report.removed:
                parts.append(b.text("added", language, items=join_and(report.added, language)))
            elif report.removed and not (report.added or report.changed):
                parts.append(b.text("removed", language, items=join_and(report.removed, language)))
            else:
                parts.append(b.text("changed", language))
        return " ".join(part for part in parts if part)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask_order", language), b.text("ask_more", language), b.text("changed", language)]


__all__ = ["ASK", "PENDING", "TOOL", "UPDATE_CART", "CartSkill"]
