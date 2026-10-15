"""The restaurant's pipeline flow: what is genuinely restaurant-specific — facts, read-back, commit, outcomes."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_BOOKED, OUTCOME_LEAD, CommitAction, CommitResult, Instruction
from app.flows.context import CallContext
from app.flows.steps import CONFIRMED
from app.flows.timefmt import calendar_facts
from app.pipeline.blueprint import Branch
from app.pipeline.flow import PipelineFlow, join
from app.verticals.common import join_and, money, notice, slot_start, when_phrase
from app.verticals.reception import caller_phone
from app.verticals.restaurant.cart import cart_phrase, items_summary, record_items, totals
from app.verticals.restaurant.config import KIND_LEAD, KIND_MENU_ITEM, KIND_ORDER, KIND_RESERVATION, LEAD, conf, num
from app.verticals.restaurant.hours import ASAP, hours_phrase, party_size, ready_at, ready_phrase, table_capacity
from app.verticals.restaurant.menu import menu_facts

RULES = """You take food orders (pickup or delivery) and table reservations for a restaurant, and answer menu questions. The system prices everything and reads the order back.
- Food: whenever the caller names dishes or drinks — to add, remove or change — call update_cart with every item of the turn in one call (never save_details for items). Pass items and options in the caller's words; the system matches the menu. If they also said pickup or delivery, include it.
- Prices: never state a price, fee, tax or total that is not in the facts or a tool result; the system computes totals.
- Menu questions: answer from the menu facts, then steer back. Allergies: answer only from the allergens listed for that item; if none are listed, say you'll need to check with the kitchen. Never guess ingredients.
- Intent: order = food for pickup or delivery; reservation = book a table; status = an order already placed; message = anything else for the team (large groups, catering, complaints).
- Reservations: save party_size, date (YYYY-MM-DD from the calendar) and time_pref (HH:MM); the system finds the free time.
- Order time: save order_time as asap, HH:MM for later today, or YYYY-MM-DD HH:MM.
- The system reads everything back and confirms; never say an order or a table is confirmed before a tool result says so."""

COMPACT_RULES = """Restaurant: food orders (pickup/delivery), table reservations, order status, menu questions.
- Dishes or drinks named (add/remove/change) → update_cart with all items of the turn, caller's words (never save_details for items).
- Never say a price or total not in the facts/tool results. Allergies: only the listed allergens, else "I'll check with the kitchen".
- Intent: order | reservation | status | message (large group, catering, complaint). Tables: party_size, date, time_pref. order_time: asap or HH:MM."""


class RestaurantFlow(PipelineFlow):
    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def intent(self, slots: dict[str, Any]) -> str:
        return str(slots.get("intent") or "order")

    # ---- a lead sentence before the next question --------------------------------------------------
    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if LEAD not in saved:
            slots.pop(LEAD, None)
        super().on_saved(saved, slots, ctx)

    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        line = super().stage_line(stage, slots, ctx, language)
        lead = slots.get(LEAD)
        if lead and isinstance(line, str):
            return join(str(lead), line)
        return line

    # ---- read-back ---------------------------------------------------------------------------------
    def order_money(self, slots: dict[str, Any], ctx: CallContext):  # noqa: ANN201
        return totals(slots.get("cart") or [], str(slots.get("fulfillment") or ""), conf(ctx))

    def amounts_line(self, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        c = self.lines
        t = self.order_money(slots, ctx)
        extras = []
        if t.delivery_fee:
            extras.append(c.text("fee", language, fee=money(t.delivery_fee, ctx, language)))
        if t.tax:
            extras.append(c.text("tax", language, tax=money(t.tax, ctx, language)))
        parts = [c.text("breakdown", language, subtotal=money(t.subtotal, ctx, language), extras=join_and(extras, language))] if extras else []
        if t.free_delivery:
            parts.append(c.text("free_delivery", language))
        parts.append(c.text("total", language, total=money(t.total, ctx, language)))
        return join(*parts)

    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        c = self.lines
        intent = self.intent(slots)
        if intent == "reservation":
            start = slot_start(slots)
            when = when_phrase(start, ctx, language) if start else ""
            summary = c.text("readback_booking", language, party=party_size(slots), when=when, name=slots.get("customer_name", ""))
            return summary, c.text("confirm_booking", language)
        if intent == "message":
            phone = caller_phone(slots, ctx)
            said = ctx.say_number(phone, language) if slots.get("phone") or not ctx.caller_number else ("this number" if language != "bn" else "এই নম্বরে")
            message = str(slots.get("message") or "").strip().rstrip(".!?।")
            return c.text("readback_message", language, message=message, phone=said), c.text("confirm_message", language)
        delivery = slots.get("fulfillment") == "delivery"
        fulfillment = c.text("delivery", language, address=slots.get("address", "")) if delivery else c.text("pickup", language)
        when = ready_phrase(slots, ctx, language, minutes_line=c.line_text("arrives_in" if delivery else "ready_in", language))
        summary = c.text("readback_order", language, items=cart_phrase(slots.get("cart") or [], language), fulfillment=fulfillment, when=when)
        return join(summary, self.amounts_line(slots, ctx, language)), c.text("confirm_order", language)

    # ---- commit ------------------------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        intent = self.intent(slots)
        name = str(slots.get("customer_name") or "")
        phone = caller_phone(slots, ctx)
        note = str(slots.get("note") or "")
        if intent == "reservation":
            start = slot_start(slots)
            if start is None:
                return None
            party = party_size(slots)
            details = {"party_size": party, "type": "reservation"}
            return CommitAction(
                outcome=OUTCOME_BOOKED,
                status="confirmed",
                fields={"kind": KIND_RESERVATION, "customer_name": name, "customer_phone": phone, "scheduled_at": start,
                        "items_summary": f"Table for {party}", "total_amount": 0, "notes": note, "details": details},
                capacity=(None, start, table_capacity(ctx, party)),
            )
        if intent == "message":
            details = {"type": "message", "message": slots.get("message", "")}
            for key in ("party_size", "date", "time_pref"):
                if slots.get(key):
                    details[key] = slots[key]
            return CommitAction(
                outcome=OUTCOME_LEAD,
                status="needs_review",
                fields={"kind": KIND_LEAD, "customer_name": name, "customer_phone": phone, "items_summary": str(slots.get("message") or ""), "notes": note, "details": details},
            )
        cart = slots.get("cart") or []
        if not cart or intent != "order":
            return None
        t = self.order_money(slots, ctx)
        delivery = slots.get("fulfillment") == "delivery"
        details = {
            "type": "order",
            "items": record_items(cart),
            "fulfillment": "delivery" if delivery else "pickup",
            "order_time": slots.get("order_time") or ASAP,
            "subtotal": t.subtotal,
            "delivery_fee": t.delivery_fee,
            "tax": t.tax,
            "tax_rate": t.tax_rate,
            "total": t.total,
            "progress": "received",
        }
        return CommitAction(
            outcome=OUTCOME_BOOKED,
            status="confirmed",
            fields={"kind": KIND_ORDER, "customer_name": name, "customer_phone": phone, "address": slots.get("address", "") if delivery else "",
                    "items_summary": items_summary(cart), "total_amount": t.total, "scheduled_at": ready_at(slots, ctx), "notes": note, "details": details},
        )

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start = slot_start(slots)
        if start is not None:
            ctx.mark_booked(None, start, 999)
        slots[CONFIRMED] = None
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- closings ------------------------------------------------------------------------------------
    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        c = self.lines
        intent = self.intent(slots)
        if outcome == OUTCOME_LEAD and intent == "message":
            return c.text("closing_message", language)
        if outcome != OUTCOME_BOOKED:
            return ""
        if intent == "reservation":
            start = slot_start(slots)
            return c.text("closing_booking", language, when=when_phrase(start, ctx, language) if start else "")
        delivery = slots.get("fulfillment") == "delivery"
        when = ready_phrase(slots, ctx, language, minutes_line=c.line_text("in_minutes", language))
        return c.text("closing_delivery" if delivery else "closing_pickup", language, when=when)

    # ---- prompt parts ----------------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return RULES

    def compact_rules(self, language: str) -> str:
        return COMPACT_RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        config = conf(ctx)
        lines = menu_facts(ctx, detail=True)
        lines.append(f"Opening hours: {hours_phrase(ctx, 'en') or 'not set'}.")
        if config.get("delivery") is False:
            lines.append("Delivery: no — pickup only.")
        else:
            parts = [f"fee {num(config.get('delivery_fee')):g}"]
            if num(config.get("free_delivery_over")):
                parts.append(f"free over {num(config.get('free_delivery_over')):g}")
            if num(config.get("minimum_order")):
                parts.append(f"minimum order {num(config.get('minimum_order')):g}")
            lines.append(f"Delivery: yes ({', '.join(parts)}), about {config.get('delivery_minutes')} minutes; pickup ready in about {config.get('prep_minutes')} minutes.")
        if num(config.get("tax_rate")):
            lines.append(f"Tax: {num(config.get('tax_rate')):g}% on food.")
        lines.append(f"Reservations: up to {config.get('max_party_size')} guests by phone; larger groups → message for the team.")
        return lines

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        assert ctx.now is not None
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.caller_number:
            lines.append(f"Caller's number: {ctx.caller_number} (used for the order unless they give another).")
        else:
            lines.append("Caller's number is unknown — the system will ask for one.")
        orders = [r for r in ctx.caller_records if str(getattr(r, "kind", "") or "") == KIND_ORDER]
        if orders:
            lines.append("This caller's recent orders: " + "; ".join(str(getattr(r, "items_summary", "") or "") for r in orders[-2:]))
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        return [str(ctx.merchant_value("business_name", "")), *[item.name for item in ctx.items(KIND_MENU_ITEM)][:20]]


__all__ = ["COMPACT_RULES", "RULES", "RestaurantFlow"]
