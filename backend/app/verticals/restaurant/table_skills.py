"""Reservations' party size (large groups become a message for the team) and order-status calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.flows.base import STAGE_DONE
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.common import when_phrase
from app.verticals.restaurant.config import KIND_ORDER, LEAD, conf, whole


class PartySizeSkill(Skill):
    key = "party_size"
    toggleable = False
    label = L2("Party size", "কতজন")
    description = L2("How many guests; groups over your maximum become a message for your team.", "কতজন অতিথি; বড় দল হলে টিমের জন্য বার্তা।")
    slots = (SlotSpec("party_size", "How many people the table is for (a number).", {"type": "integer"}),)
    volunteerable = frozenset({"party_size"})
    lines = (
        line("party_size", "How many people is the table for?", "কতজনের জন্য টেবিল লাগবে?", label="Ask how many", static=True),
        line("too_big", "For groups larger than {max}, our team arranges it personally — I'll pass on your details.", "{max} জনের বেশি দলের জন্য আমাদের টিম নিজে ব্যবস্থা করে — আমি আপনার তথ্য পৌঁছে দিচ্ছি।", label="Group too large", variables=("max",)),
    )
    goal = "How many people is the table for?"

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return slots.get("intent") == "reservation"

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        size = whole(fields.get("party_size"), 0)
        if size < 1 or size > 500:
            fields.pop("party_size", None)
            return fields, None
        fields["party_size"] = size
        limit = whole(conf(ctx).get("max_party_size"), 0)
        if limit and size > limit and slots.get("intent") in (None, "", "reservation"):
            # Too big to book by phone: a message for the team (the message branch takes over;
            # the date / time they mentioned travel with it in the record's details).
            fields["intent"] = "message"
            fields["message"] = f"Table for {size} people"
            fields[LEAD] = b.text("too_big", language, max=limit)
        return fields, None

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("party_size", language)]


PROGRESS = ("received", "preparing", "ready", "out_for_delivery", "completed")


class StatusSkill(Skill):
    """Reads the status of the caller's latest order (found by phone number), then offers more help."""

    key = "status"
    toggleable = False
    label = L2("Order status", "অর্ডারের অবস্থা")
    description = L2("Tells callers where their order is.", "কলারকে অর্ডারের অবস্থা জানায়।")
    slots = (
        SlotSpec("more_help", "After the order status: true = they need something else, false = no.", {"type": "boolean"}, directions=("inbound",)),
        SlotSpec("order_instead", "No order found: true = they want to order now, false = no.", {"type": "boolean"}, directions=("inbound",)),
    )
    yes_no = {"order_status": "more_help", "no_order_found": "order_instead"}
    stage_slots = {"order_status": ("more_help",), "no_order_found": ("order_instead",)}
    lines = (
        line("preparing", "Your order of {items} is being prepared — it should be ready {when}.", "আপনার অর্ডার ({items}) তৈরি হচ্ছে — {when} রেডি হওয়ার কথা।", label="Being prepared (pickup)", variables=("items", "when")),
        line("preparing_delivery", "Your order of {items} is being prepared — it should arrive {when}.", "আপনার অর্ডার ({items}) তৈরি হচ্ছে — {when} পৌঁছানোর কথা।", label="Being prepared (delivery)", variables=("items", "when")),
        line("ready", "Your order is ready for pickup.", "আপনার অর্ডার রেডি, এসে নিয়ে যেতে পারেন।", label="Ready", static=True),
        line("on_the_way", "Your order is on its way.", "আপনার অর্ডার পথে আছে।", label="On the way", static=True),
        line("completed", "That order has been completed.", "অর্ডারটি সম্পন্ন হয়েছে।", label="Completed", static=True),
        line("cancelled", "That order was cancelled.", "অর্ডারটি বাতিল করা হয়েছে।", label="Cancelled", static=True),
        line("review", "Our team is checking your order and will call you if anything's needed.", "আমাদের টিম আপনার অর্ডার দেখছে, দরকার হলে ফোন করবে।", label="Being checked", static=True),
        line("more", "Is there anything else I can help with?", "আর কিছুতে সাহায্য করতে পারি?", label="Anything else", static=True),
        line("none", "I can't find a recent order for this number. Would you like to place one?", "এই নম্বরে সাম্প্রতিক কোনো অর্ডার পাচ্ছি না। নতুন অর্ডার করবেন?", label="Nothing found", static=True),
    )
    goal = "The system read the order status: save more_help (or the new intent if they want something else)."

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return slots.get("intent") == "status"

    @staticmethod
    def latest(ctx: CallContext) -> Any | None:
        orders = [r for r in ctx.caller_records if str(getattr(r, "kind", "") or "") == KIND_ORDER]
        stamp = lambda r: getattr(r, "scheduled_at", None) or datetime.min.replace(tzinfo=ctx.now.tzinfo)  # noqa: E731
        return max(orders, key=stamp) if orders else None

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("order_status", "no_order_found")

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if self.latest(ctx) is None:
            return "no_order_found" if slots.get("order_instead") is None else STAGE_DONE
        return "order_status" if slots.get("more_help") is None else STAGE_DONE

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if "intent" in saved:
            slots.pop("more_help", None)
            slots.pop("order_instead", None)
            return
        if saved.get("order_instead") is True:
            slots["intent"] = "order"
        elif saved.get("more_help") is True:
            slots["intent"] = None  # back to "How can I help?"
            slots.pop("more_help", None)

    def status_line(self, b: BoundSkill, record: Any, ctx: CallContext, language: str) -> str:
        details = getattr(record, "details", None) or {}
        status = str(getattr(getattr(record, "status", ""), "value", getattr(record, "status", "")) or "")
        progress = str(details.get("progress") or "")
        if status == "cancelled":
            return b.text("cancelled", language)
        if progress in ("ready", "out_for_delivery", "completed"):
            return b.text({"ready": "ready", "out_for_delivery": "on_the_way", "completed": "completed"}[progress], language)
        if status == "needs_review":
            return b.text("review", language)
        start = getattr(record, "scheduled_at", None)
        when = when_phrase(start.astimezone(ctx.now.tzinfo), ctx, language) if isinstance(start, datetime) else ""
        key = "preparing_delivery" if details.get("fulfillment") == "delivery" else "preparing"
        items = str(getattr(record, "items_summary", "") or "").replace("×", "")
        return b.text(key, language, items=items, when=when)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        record = self.latest(ctx)
        if stage == "no_order_found" or record is None:
            return b.text("none", language)
        return f"{self.status_line(b, record, ctx, language)} {b.text('more', language)}"

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("none", language), b.text("more", language)]


__all__ = ["PROGRESS", "PartySizeSkill", "StatusSkill"]
