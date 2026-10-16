"""The real-estate pipeline flow: what is genuinely real-estate — facts, read-back, lead commit, outcomes."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_BOOKED, OUTCOME_LEAD, OUTCOME_NOT_INTERESTED, STAGE_COMMIT, CommitAction, CommitResult, Instruction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import CONFIRMED, DECISION
from app.flows.timefmt import calendar_facts
from app.pipeline.blueprint import Branch
from app.pipeline.flow import PipelineFlow
from app.verticals.common import notice, slot_start, when_phrase
from app.verticals.real_estate.catalog import (
    INTENT_WORDS,
    KIND_LEAD,
    KIND_PROPERTY,
    LEAD_KEYS,
    TYPE_WORDS,
    chosen_property,
    interest_phrase,
    lead_score,
    listing_facts,
    visit_capacity,
    word,
)
from app.verticals.reception.contact import caller_phone
from app.voice.languages import normalize_language

RULES = """You are the phone assistant of a real-estate agency (land, plots, apartments / flats, houses, commercial space). You qualify buyers, renters and sellers and book property viewings (site visits); a human agent follows up.
- Use the size units and price words the caller uses (square feet / metres, acres; katha, bigha, lakh and crore in South Asia). Say prices in words.
- Only describe listings from the list below, with their real size and price. Never promise a price, a discount, a valuation, a return on investment, or legal / title / mutation status — say the agent will discuss it, or call transfer_to_human for negotiation.
- Save details as the caller gives them: intent (buy / rent / sell), property_type, location (the area they want or where their property is), budget as they said it plus budget_max as a plain number in the account's currency when clear (e.g. "450k" = 450000; 1 lakh = 100000, 1 crore = 10000000), size, timeline, asking_price (sellers).
- Listings are referred to by ref (P1, P2, …); save the one the caller likes as `property`.
- Site visit: save visit_date as YYYY-MM-DD from the calendar below and visit_time_pref as HH:MM or morning/afternoon/evening; the system picks the time, reads it back and books it.
- Never say a visit is booked before a tool result says so. Never discriminate between callers."""

COMPACT_RULES = """Real-estate assistant: qualify buyers, renters and sellers; book viewings; an agent follows up.
- Save intent (buy/rent/sell), property_type, location, budget (+ budget_max as a number), size, timeline, asking_price as given.
- Describe only listed properties (refs P1…, save the liked one as `property`); prices in words. Never promise prices, valuations or legal status.
- Viewing: save visit_date (YYYY-MM-DD) + visit_time_pref; the system picks the time. Never discriminate."""


class RealEstateFlow(PipelineFlow):
    RULES = RULES
    COMPACT_RULES = COMPACT_RULES

    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def record_id(self, ctx: CallContext) -> str | None:
        return (str(getattr(ctx.record, "id", "") or "") or None) if ctx.direction != DIRECTION_INBOUND else None

    # ---- slots -----------------------------------------------------------------------------------
    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        slots = super().initial_slots(ctx)
        if ctx.direction == DIRECTION_INBOUND or ctx.record is None:
            return slots
        details = ctx.record_details()
        slots["caller_name"] = ctx.record_value("customer_name", "")
        for key in ("intent", "property_type", "location", "budget", "budget_max", "size", "timeline"):
            if details.get(key) not in (None, ""):
                slots[key] = details[key]
        item = ctx.item_by_id(getattr(ctx.record, "catalog_item_id", None))
        if item is not None:
            slots["property"] = item.ref
        return slots

    def tail(self, slots: dict[str, Any]) -> str:
        if not slots.get(DECISION) and slots.get("intent") in ("buy", "rent") and slots.get("wants_visit") is False:
            return STAGE_COMMIT  # no visit: nothing to read back — the lead goes to an agent
        return super().tail(slots)

    # ---- read-back -------------------------------------------------------------------------------
    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        lang = normalize_language(language)
        if slots.get("intent") == "sell":
            text = self.lines.text(
                "readback_sell",
                lang,
                area=slots.get("location", ""),
                type=word(TYPE_WORDS, slots.get("property_type"), lang),
                size=slots.get("size", ""),
                price=slots.get("asking_price", ""),
            )
            return text, ""
        start = slot_start(slots)
        summary = self.lines.text(
            "readback_visit",
            lang,
            name=slots.get("caller_name", ""),
            when=when_phrase(start, ctx, lang, on=True) if start else "",
            what=interest_phrase(slots, ctx, lang),
        )
        return summary, self.lines.text("confirm_visit", lang)

    # ---- commit ----------------------------------------------------------------------------------
    def lead_fields(self, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        item = chosen_property(slots, ctx)
        details = {key: slots[key] for key in LEAD_KEYS if slots.get(key) not in (None, "")}
        details["lead_score"] = lead_score(slots)
        if slots.get("wants_visit") is not None:
            details["wants_visit"] = bool(slots.get("wants_visit"))
        summary = " · ".join(
            part
            for part in (
                word(INTENT_WORDS, slots.get("intent"), "en").capitalize() if slots.get("intent") else "",
                word(TYPE_WORDS, slots.get("property_type"), "en") if slots.get("property_type") else "",
                str(slots.get("location") or ""),
                str(slots.get("budget") or slots.get("asking_price") or ""),
            )
            if part
        )
        fields: dict[str, Any] = {
            "kind": KIND_LEAD,
            "customer_name": slots.get("caller_name", "") or ctx.record_value("customer_name", ""),
            "customer_phone": caller_phone(slots, ctx) or ctx.record_value("customer_phone", ""),
            "items_summary": summary,
            "details": details,
        }
        if item is not None:
            fields["catalog_item_id"] = item.id
        return fields

    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        record_id = self.record_id(ctx)
        if ctx.direction != DIRECTION_INBOUND and slots.get("still_interested") is False:
            return CommitAction(outcome=OUTCOME_NOT_INTERESTED, status="cancelled", record_id=record_id)
        fields = self.lead_fields(slots, ctx)
        start = slot_start(slots)
        if slots.get("wants_visit") is True and start is not None:
            fields["scheduled_at"] = start
            return CommitAction(outcome=OUTCOME_BOOKED, status="confirmed", record_id=record_id, fields=fields, capacity=(None, start, visit_capacity(ctx)))
        return CommitAction(outcome=OUTCOME_LEAD, status="needs_review", record_id=record_id, fields=fields)

    def fallback_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        """An inbound caller who hung up mid-way is still a lead if we know who they are."""
        if ctx.direction != DIRECTION_INBOUND or not (slots.get("intent") or slots.get("property_type")):
            return None
        if not caller_phone(slots, ctx):
            return None
        return CommitAction(outcome=OUTCOME_LEAD, status="needs_review", fields=self.lead_fields(slots, ctx))

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start = slot_start(slots)
        if start is not None:
            ctx.mark_booked(None, start, 99)
        slots[CONFIRMED] = None
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    # ---- closings ------------------------------------------------------------------------------------
    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if outcome == OUTCOME_BOOKED:
            start = slot_start(slots)
            return self.lines.text("closing_visit", language, when=when_phrase(start, ctx, language) if start else "")
        if outcome == OUTCOME_LEAD:
            return self.lines.text("closing_seller" if slots.get("intent") == "sell" else "closing_lead", language)
        if outcome == OUTCOME_NOT_INTERESTED:
            return self.lines.text("closing_not_interested", language)
        return ""

    def knows_person_line(self, ctx: CallContext, language: str) -> str:
        return self.lines.text("knows_person", language, name=self.person_name(ctx))

    # ---- prompt parts ----------------------------------------------------------------------------------
    def rules(self, language: str) -> str:
        return self.RULES

    def compact_rules(self, language: str) -> str:
        return self.COMPACT_RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        return listing_facts(ctx)

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.direction == DIRECTION_INBOUND:
            lines.append(f"Caller's number: {ctx.caller_number}." if ctx.caller_number else "Caller's number is unknown — the system will ask for it.")
        else:
            details = ctx.record_details()
            known = ", ".join(f"{key}: {value}" for key, value in details.items() if key != "lead_score" and value not in (None, ""))
            lines.append(f"This is a follow-up call to a lead: {self.person_name(ctx)}. Known so far: {known or 'nothing yet'}.")
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [str(item.get("location", "")) for item in ctx.items(KIND_PROPERTY)][:8]
        return hints


__all__ = ["COMPACT_RULES", "RULES", "RealEstateFlow"]
