"""Real-estate engine: a land / flat broker's phone line.

Inbound — a buyer, renter or seller calls:

    intent ─ buy/rent ─▶ name → property type → area → budget → timeline
           │             → listings that fit (model) → site visit? ─ yes → day → read-back → visit booked
           │                                                       └ no → lead for the broker
           └ sell ─────▶ name → property type → area → size → asking price → read-back → seller lead

Outbound — the broker follows up a lead:

    identity → still interested? ─ no → not interested
                                 └ yes → (missing details) → listings → visit → ...

Leads are scored in code (hot / warm / cold) from timeline and visit, never by
the model. Prices, valuations and legal status are never promised.
"""

from __future__ import annotations

import re
from typing import Any

from app.flows.base import (
    OUTCOME_BOOKED,
    OUTCOME_LEAD,
    OUTCOME_NOT_INTERESTED,
    STAGE_COMMIT,
    CommitAction,
    CommitResult,
    Instruction,
)
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.flows.steps import CONFIRMED, STAGE_CONFIRM, SlotSpec, StepFlow, lang_text
from app.flows.timefmt import calendar_facts
from app.verticals.base import FieldSpec, L, Vertical
from app.verticals.common import clear_notice, notice, plan_booking, schedule_phrase, slot_start, when_phrase, with_notice
from app.verticals.reception import PHONE_HINT, caller_phone, clean_phone
from app.voice.languages import normalize_language, phrase

KIND_PROPERTY = "property"
KIND_LEAD = "lead"

INTENT = "intent"
NAME = "caller_name"
TYPE = "property_type"
AREA = "location"
BUDGET = "budget"
SIZE = "size"
PRICE = "asking_price"
TIMELINE = "timeline"
PITCH = "listings"
VISIT_DATE = "visit_date"
PHONE = "phone"
INTERESTED = "still_interested"

PROPERTY_TYPES = ["land", "flat", "house", "commercial"]
TIMELINES = ["now", "1-3 months", "3-6 months", "later"]

_TYPE_WORDS = {
    "land": {"bn": "জমি", "en": "land"},
    "flat": {"bn": "ফ্ল্যাট", "en": "apartment"},
    "house": {"bn": "বাড়ি", "en": "house"},
    "commercial": {"bn": "কমার্শিয়াল স্পেস", "en": "commercial space"},
}
_INTENT_WORDS = {
    "buy": {"bn": "কেনা", "en": "buying"},
    "rent": {"bn": "ভাড়া", "en": "renting"},
    "sell": {"bn": "বিক্রি", "en": "selling"},
}

_LINES: dict[str, dict[str, str]] = {
    "opening_question": {
        "bn": "আপনি কি জমি বা ফ্ল্যাট কিনতে, ভাড়া নিতে, নাকি বিক্রি করতে চান?",
        "en": "Are you looking to buy, rent, or sell a property?",
    },
    "intent": {
        "bn": "আপনি কি কিনতে চান, ভাড়া নিতে চান, নাকি আপনার জমি বা ফ্ল্যাট বিক্রি করতে চান?",
        "en": "Are you looking to buy, to rent, or to sell your property?",
    },
    "caller_name": {"bn": "আপনার নামটা একটু বলবেন?", "en": "May I have your name, please?"},
    "property_type": {
        "bn": "কী ধরনের প্রপার্টি — জমি বা প্লট, ফ্ল্যাট, বাড়ি, নাকি কমার্শিয়াল?",
        "en": "What kind of property — an apartment, a house, land, or commercial space?",
    },
    "location": {"bn": "কোন এলাকায় খুঁজছেন?", "en": "Which area are you looking in?"},
    "location_sell": {"bn": "প্রপার্টিটা কোন এলাকায়?", "en": "Where is the property located?"},
    "budget": {"bn": "আপনার বাজেট মোটামুটি কত?", "en": "Roughly what is your budget?"},
    "budget_rent": {"bn": "মাসিক ভাড়ার বাজেট কত?", "en": "What monthly rent are you looking at?"},
    "size": {"bn": "জায়গাটা কত বড় — কত কাঠা বা কত স্কয়ার ফিট?", "en": "How big is it?"},
    "asking_price": {"bn": "কত দাম আশা করছেন?", "en": "What price are you expecting?"},
    "timeline": {"bn": "কবের মধ্যে নিতে চান — এখনই, নাকি কয়েক মাসের মধ্যে?", "en": "When are you planning to buy — right away, or in the next few months?"},
    "timeline_rent": {"bn": "কবে থেকে উঠতে চান?", "en": "When would you like to move in?"},
    "visit_date": {
        "bn": "কোন দিন সাইট ভিজিটে আসতে চান? আমরা {schedule} সাইট দেখাই।",
        "en": "Which day would you like to come for a viewing? We do viewings {schedule}.",
    },
    "phone": {"bn": "আপনার মোবাইল নম্বরটা বলবেন?", "en": "What's the best mobile number to reach you?"},
    "readback_visit": {
        "bn": "তাহলে {name}, {when} {what} দেখতে সাইট ভিজিট — আমাদের প্রতিনিধি আগের দিন ফোন করে ঠিকানা জানিয়ে দেবেন। ভিজিটটা কনফার্ম করব?",
        "en": "So, {name}, a viewing of {what} {when} — our agent will call the day before with the meeting point. Shall I confirm it?",
    },
    "readback_sell": {
        "bn": "তাহলে {area}-এ আপনার {type}, {size}, দাম আশা করছেন {price}। আমাদের প্রতিনিধি আপনার সাথে যোগাযোগ করবেন — ঠিক আছে?",
        "en": "So your {type} in {area}, {size}, asking {price}. Our agent will get in touch with you — is that right?",
    },
    "still_interested": {
        "bn": "আপনি আমাদের কাছে {interest} নিয়ে জানতে চেয়েছিলেন। এখনও কি আগ্রহী আছেন?",
        "en": "You had asked us about {interest}. Are you still interested?",
    },
    "closing_visit": {
        "bn": "আপনার সাইট ভিজিট কনফার্ম হয়েছে — {when}। আমাদের প্রতিনিধি আগের দিন ফোন করবেন। ধন্যবাদ, ভালো থাকবেন।",
        "en": "Your viewing is confirmed — {when}. Our agent will call you the day before. Thank you, goodbye.",
    },
    "closing_lead": {
        "bn": "ধন্যবাদ। আমাদের একজন প্রতিনিধি শীঘ্রই আপনাকে ফোন করে আরও অপশন জানাবেন। ভালো থাকবেন।",
        "en": "Thank you. One of our agents will call you shortly with more options. Goodbye.",
    },
    "closing_seller": {
        "bn": "ধন্যবাদ। আমাদের একজন প্রতিনিধি শীঘ্রই আপনার প্রপার্টি বিক্রির ব্যাপারে ফোন করবেন। ভালো থাকবেন।",
        "en": "Thank you. One of our agents will call you shortly about selling your property. Goodbye.",
    },
    "closing_not_interested": {
        "bn": "ঠিক আছে, সময় দেওয়ার জন্য ধন্যবাদ। কখনো দরকার হলে ফোন করবেন। ভালো থাকবেন।",
        "en": "Alright, thank you for your time. Call us any time you need. Goodbye.",
    },
    "knows_person": {
        "bn": "{name} আমাদের কাছে একটি প্রপার্টির ব্যাপারে জানতে চেয়েছিলেন। আপনি কি ওনাকে চেনেন?",
        "en": "{name} had asked us about a property. Do you know them?",
    },
}

_PITCH_GUIDE = {
    "bn": (
        "এখন তালিকা থেকে কলারের চাহিদার (ধরন, এলাকা, বাজেট) সাথে মেলে এমন সর্বোচ্চ দুটি প্রপার্টি এক-দুই ছোট বাক্যে বলুন — "
        "এলাকা, আকার আর দাম কথায় — তারপর জিজ্ঞেস করুন সাইট ভিজিট করতে চান কি না। মিলে যাওয়ার মতো কিছু না থাকলে সৎভাবে বলুন "
        "এবং জিজ্ঞেস করুন প্রতিনিধি অন্য অপশন নিয়ে ফোন করলে ঠিক আছে কি না (তখন wants_visit=false)। কলার কোনো প্রপার্টি বাছলে property=<ref> সেভ করুন।"
    ),
    "en": (
        "Now tell the caller, in one or two short sentences, about at most two listings that fit their needs (type, area, budget) — "
        "area, size and price in words — then ask whether they'd like a site visit. If nothing fits, say so honestly and ask whether "
        "an agent may call with other options (then wants_visit=false). When the caller picks a listing, save property=<ref>."
    ),
}

_RULES = """You are the phone assistant of a real-estate agency (land, plots, apartments / flats, houses, commercial space). You qualify buyers, renters and sellers and book property viewings (site visits); a human agent follows up.
- Use the size units and price words the caller uses (square feet / metres, acres; katha, bigha, lakh and crore in South Asia). Say prices in words.
- Only describe listings from the list below, with their real size and price. Never promise a price, a discount, a valuation, a return on investment, or legal / title / mutation status — say the agent will discuss it, or call transfer_to_human for negotiation.
- Save details as the caller gives them: intent (buy / rent / sell), property_type, location (the area they want or where their property is), budget as they said it plus budget_max as a plain number in the account's currency when clear (e.g. "450k" = 450000; 1 lakh = 100000, 1 crore = 10000000), size, timeline, asking_price (sellers).
- Listings are referred to by ref (P1, P2, …); save the one the caller likes as `property`.
- Site visit: save visit_date as YYYY-MM-DD from the calendar below and visit_time_pref as HH:MM or morning/afternoon/evening; the system picks the time, reads it back and books it.
- Never say a visit is booked before a tool result says so. Never discriminate between callers."""


def visit_availability(ctx: CallContext) -> Availability | None:
    config = REAL_ESTATE.config(ctx.merchant)
    window = window_from_config(
        {
            "days": config.get("visit_days") or [],
            "start": config.get("visit_start"),
            "end": config.get("visit_end"),
            "slot_minutes": config.get("visit_slot_minutes") or 60,
            "capacity": config.get("visit_capacity") or 1,
        },
        default_step=60,
    )
    if window is None:
        return None
    return Availability(
        windows=[window],
        item_id=None,
        horizon_days=int(config.get("booking_horizon_days") or 14),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 120),
        busy=ctx.busy_for(None),
    )


def _word(table: dict[str, dict[str, str]], key: Any, language: str) -> str:
    entry = table.get(str(key or ""))
    return lang_text(entry, language) if entry else str(key or "")


def _number(value: Any) -> float | None:
    try:
        number = float(re.sub(r"[^\d.]", "", str(value)))
    except ValueError:
        return None
    return number if number > 0 else None


def lead_score(slots: dict[str, Any]) -> str:
    if slots.get("intent") == "sell":
        return "warm"
    if slots.get("wants_visit") is True or slots.get("timeline") == "now":
        return "hot"
    if slots.get("timeline") in ("1-3 months",) or slots.get("budget"):
        return "warm"
    return "cold"


class RealEstateFlow(StepFlow):
    vertical = "real_estate"
    long_answer_stages = frozenset({AREA, BUDGET, SIZE, PRICE, PHONE})

    def __init__(self, direction: str) -> None:
        self.direction = direction
        self.key = f"real_estate.{direction}"
        self.identity_gate = direction != DIRECTION_INBOUND

    slot_specs = (
        SlotSpec("intent", "What the caller wants.", {"type": "string", "enum": ["buy", "rent", "sell"]}),
        SlotSpec("caller_name", "The caller's name."),
        SlotSpec("property_type", "Kind of property.", {"type": "string", "enum": PROPERTY_TYPES}),
        SlotSpec("location", "Area they want (buyers/renters) or where their property is (sellers), as said."),
        SlotSpec("budget", "Budget as the caller said it (e.g. '৫০-৬০ লাখ', '25 thousand a month')."),
        SlotSpec("budget_max", "Upper end of the budget as a plain number in the account's currency, when clear.", {"type": "number"}),
        SlotSpec("size", "Size as said (e.g. '৫ কাঠা', '1200 sq ft', '3 bed')."),
        SlotSpec("asking_price", "Sellers: the price they expect, as said."),
        SlotSpec("timeline", "When they plan to buy / move.", {"type": "string", "enum": TIMELINES}),
        SlotSpec("property", "The listing the caller is interested in (ref P1, P2, …)."),
        SlotSpec("wants_visit", "true = they want a site visit; false = no visit now (an agent calls back).", {"type": "boolean"}),
        SlotSpec("visit_date", "Viewing date as YYYY-MM-DD. Convert a day the caller names ('Saturday', 'tomorrow') with the calendar in the facts."),
        SlotSpec("visit_time_pref", "Preferred visit time: HH:MM (24 h) or morning / afternoon / evening."),
        SlotSpec("phone", f"Mobile number, digits only. {PHONE_HINT}"),
        SlotSpec("still_interested", "Follow-up call: true = still interested, false = not interested any more.", {"type": "boolean"}, gated=True, directions=('outbound',)),
    )
    yes_no_stages = {STAGE_CONFIRM: CONFIRMED, PITCH: "wants_visit", INTERESTED: "still_interested"}
    stage_goals = {
        INTENT: "Find out whether they want to buy, rent, or sell.",
        NAME: "Get the caller's name.",
        TYPE: "Which kind of property (land, flat, house, commercial)?",
        AREA: "Which area?",
        BUDGET: "Their budget.",
        SIZE: "Size of the seller's property.",
        PRICE: "The seller's expected price.",
        TIMELINE: "When they plan to buy or move.",
        PITCH: "Present at most two fitting listings and ask about a site visit (see the instruction).",
        VISIT_DATE: "Which day for the site visit (and a preferred time if they say one).",
        PHONE: "A mobile number to reach them.",
        INTERESTED: "Are they still interested?",
    }
    stage_slots = {
        INTENT: ("intent",),
        NAME: ("caller_name",),
        TYPE: ("property_type",),
        AREA: ("location",),
        BUDGET: ("budget", "budget_max"),
        SIZE: ("size",),
        PRICE: ("asking_price",),
        TIMELINE: ("timeline",),
        PITCH: ("property", "wants_visit"),
        VISIT_DATE: ("visit_date", "visit_time_pref"),
        PHONE: ("phone",),
        INTERESTED: ("still_interested",),
    }

    @property
    def gated_slots(self) -> tuple[str, ...]:  # type: ignore[override]
        return ("still_interested", CONFIRMED)

    # ---- context -------------------------------------------------------------------
    def _property(self, slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
        found = ctx.find_items(slots.get("property"), KIND_PROPERTY) if slots.get("property") else []
        return found[0] if len(found) == 1 else None

    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        if ctx.direction == DIRECTION_INBOUND or ctx.record is None:
            return {}
        details = ctx.record_details()
        slots: dict[str, Any] = {"caller_name": ctx.record_value("customer_name", "")}
        for key in ("intent", "property_type", "location", "budget", "budget_max", "size", "timeline"):
            if details.get(key) not in (None, ""):
                slots[key] = details[key]
        item = ctx.item_by_id(getattr(ctx.record, "catalog_item_id", None))
        if item is not None:
            slots["property"] = item.ref
        return slots

    def normalize(self, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        fields = dict(fields)
        if "property" in fields:
            found = ctx.find_items(fields["property"], KIND_PROPERTY, fields=("location",))
            if len(found) == 1:
                fields["property"] = found[0].ref
            else:
                fields.pop("property")
        if "phone" in fields:
            phone = clean_phone(fields["phone"])
            if not phone:
                fields.pop("phone")
                return fields, Instruction(PHONE, phrase("phone_invalid", language), verbatim=True)
            fields["phone"] = phone
        if "budget_max" in fields and _number(fields["budget_max"]) is None:
            fields.pop("budget_max")
        return fields, None

    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        clear_notice(slots)
        super().on_saved(saved, slots, ctx)
        if saved.get("visit_date") or saved.get("visit_time_pref"):
            slots["wants_visit"] = True

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        if slots.get("wants_visit") is True:
            plan_booking(slots, ctx, visit_availability(ctx), date_key="visit_date", pref_key="visit_time_pref")
        else:
            for key in ("slot", "serial"):
                slots.pop(key, None)

    # ---- cascade -------------------------------------------------------------------
    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        gate = self.identity_stage(slots)
        if gate is not None:
            return gate
        if slots.get("decision"):
            return self.tail(slots)
        if ctx.direction != DIRECTION_INBOUND:
            interested = slots.get("still_interested")
            if interested is None:
                return INTERESTED
            if interested is False:
                return STAGE_COMMIT
        intent = slots.get("intent")
        if not intent:
            return INTENT
        if not slots.get("caller_name"):
            return NAME
        if not slots.get("property_type"):
            return TYPE
        if not slots.get("location"):
            return AREA
        if intent == "sell":
            if not slots.get("size"):
                return SIZE
            if not slots.get("asking_price"):
                return PRICE
            if not caller_phone(slots, ctx):
                return PHONE
            return self.tail(slots)
        if not slots.get("budget") and not slots.get("budget_max"):
            return BUDGET
        if not slots.get("timeline"):
            return TIMELINE
        wants = slots.get("wants_visit")
        if wants is None:
            return PITCH
        if wants is True and not (slots.get("visit_date") and slots.get("slot")):
            return VISIT_DATE
        if not caller_phone(slots, ctx):
            return PHONE
        if wants is False:
            # No visit: nothing to read back — the lead goes to an agent.
            return STAGE_COMMIT
        return self.tail(slots)

    # ---- lines ---------------------------------------------------------------------
    def opening_question(self, ctx: CallContext, language: str) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return lang_text(_LINES["opening_question"], language)
        return super().opening_question(ctx, language)

    def greeting(self, ctx: CallContext, language: str) -> str:
        if ctx.direction == DIRECTION_INBOUND:
            return self.inbound_greeting(ctx, language)
        return super().greeting(ctx, language)

    def knows_person_line(self, ctx: CallContext, language: str) -> str:
        return lang_text(_LINES["knows_person"], language).format(name=self.person_name(ctx))

    def matching_listings(self, slots: dict[str, Any], ctx: CallContext, limit: int = 4) -> list[CatalogEntry]:
        """Listings of the right kind for the caller (type, sale/rent, budget). Area fit is the model's call."""
        intent = slots.get("intent")
        wanted_listing = "rent" if intent == "rent" else "sale"
        ptype = slots.get("property_type")
        budget = _number(slots.get("budget_max"))
        out: list[CatalogEntry] = []
        for item in ctx.items(KIND_PROPERTY):
            if str(item.get("listing_type", "sale")) != wanted_listing:
                continue
            if ptype and item.get("property_type") and item.get("property_type") != ptype:
                continue
            price = _number(item.get("price"))
            if budget and price and price > budget * 1.25:
                continue
            out.append(item)
        return out[:limit]

    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        rent = slots.get("intent") == "rent"
        if stage == PITCH:
            fits = self.matching_listings(slots, ctx)
            refs = ", ".join(item.ref for item in fits) or ("কোনোটিই নয়" if lang == "bn" else "none")
            lead = "মিলতে পারে এমন" if lang == "bn" else "Listings that may fit"
            return Instruction(stage, f"{lang_text(_PITCH_GUIDE, lang)} ({lead}: {refs})")
        texts = {
            INTENT: t("intent"),
            NAME: t("caller_name"),
            TYPE: t("property_type"),
            AREA: t("location_sell") if slots.get("intent") == "sell" else t("location"),
            BUDGET: t("budget_rent") if rent else t("budget"),
            SIZE: t("size"),
            PRICE: t("asking_price"),
            TIMELINE: t("timeline_rent") if rent else t("timeline"),
            PHONE: t("phone"),
        }
        if stage in texts:
            return with_notice(slots, ctx, lang, texts[stage])
        if stage == VISIT_DATE:
            availability = visit_availability(ctx)
            schedule = schedule_phrase(availability, lang, ctx) if availability else ""
            return with_notice(slots, ctx, lang, t("visit_date").format(schedule=schedule))
        if stage == INTERESTED:
            return t("still_interested").format(interest=self._interest_phrase(slots, ctx, lang))
        if stage == STAGE_CONFIRM:
            return with_notice(slots, ctx, lang, self._readback(slots, ctx, lang))
        return ""

    def _interest_phrase(self, slots: dict[str, Any], ctx: CallContext, lang: str) -> str:
        item = self._property(slots, ctx)
        if item is not None:
            return item.name if lang == "bn" else f"the {item.name}"
        ptype = _word(_TYPE_WORDS, slots.get("property_type"), lang) if slots.get("property_type") else ""
        area = slots.get("location") or ""
        if lang == "bn":
            return " ".join(part for part in (area, ptype) if part) or "একটি প্রপার্টি"
        return " ".join(part for part in (ptype, f"in {area}" if area else "") if part) or "a property"

    def _readback(self, slots: dict[str, Any], ctx: CallContext, lang: str) -> str:
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        if slots.get("intent") == "sell":
            return t("readback_sell").format(
                area=slots.get("location", ""),
                type=_word(_TYPE_WORDS, slots.get("property_type"), lang),
                size=slots.get("size", ""),
                price=slots.get("asking_price", ""),
            )
        start = slot_start(slots)
        return t("readback_visit").format(
            name=slots.get("caller_name", ""),
            when=when_phrase(start, ctx, lang, on=True) if start else "",
            what=self._interest_phrase(slots, ctx, lang),
        )

    # ---- commit --------------------------------------------------------------------
    def _lead_fields(self, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        item = self._property(slots, ctx)
        details = {
            key: slots[key]
            for key in ("intent", "property_type", "location", "budget", "budget_max", "size", "asking_price", "timeline")
            if slots.get(key) not in (None, "")
        }
        details["lead_score"] = lead_score(slots)
        if slots.get("wants_visit") is not None:
            details["wants_visit"] = bool(slots.get("wants_visit"))
        summary = " · ".join(
            part
            for part in (
                _word(_INTENT_WORDS, slots.get("intent"), "en").capitalize() if slots.get("intent") else "",
                _word(_TYPE_WORDS, slots.get("property_type"), "en") if slots.get("property_type") else "",
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

    def commit_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        record_id = (str(getattr(ctx.record, "id", "") or "") or None) if ctx.direction != DIRECTION_INBOUND else None
        if ctx.direction != DIRECTION_INBOUND and slots.get("still_interested") is False:
            return CommitAction(outcome=OUTCOME_NOT_INTERESTED, status="cancelled", record_id=record_id)
        fields = self._lead_fields(slots, ctx)
        start = slot_start(slots)
        if slots.get("wants_visit") is True and start is not None:
            fields["scheduled_at"] = start
            config = REAL_ESTATE.config(ctx.merchant)
            return CommitAction(
                outcome=OUTCOME_BOOKED,
                status="confirmed",
                record_id=record_id,
                fields=fields,
                capacity=(None, start, int(config.get("visit_capacity") or 1)),
            )
        return CommitAction(outcome=OUTCOME_LEAD, status="needs_review", record_id=record_id, fields=fields)

    def fallback_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        """An inbound caller who hung up mid-way is still a lead if we know who they are."""
        if ctx.direction != DIRECTION_INBOUND or not (slots.get("intent") or slots.get("property_type")):
            return None
        if not caller_phone(slots, ctx):
            return None
        return CommitAction(outcome=OUTCOME_LEAD, status="needs_review", fields=self._lead_fields(slots, ctx))

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

    def closing_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        if outcome == OUTCOME_BOOKED:
            start = slot_start(slots)
            return t("closing_visit").format(when=when_phrase(start, ctx, lang) if start else "")
        if outcome == OUTCOME_LEAD:
            return t("closing_seller") if slots.get("intent") == "sell" else t("closing_lead")
        if outcome == OUTCOME_NOT_INTERESTED:
            return t("closing_not_interested")
        return super().closing_line(outcome, slots, ctx, lang)

    # ---- prompt parts ----------------------------------------------------------------
    def rules(self, language: str) -> str:
        return _RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [f"Listings (ref: title — for sale/rent, type, area, size, price in {ctx.currency}, details):"]
        for item in ctx.items(KIND_PROPERTY):
            parts = [f"{item.ref}: {item.name}", f"— {item.get('listing_type', 'sale')}", str(item.get("property_type", ""))]
            for key in ("location", "size"):
                if item.get(key):
                    parts.append(f"; {item.get(key)}")
            if item.get("price"):
                unit = " per month" if item.get("listing_type") == "rent" else ""
                parts.append(f"; price {item.get('price')} {ctx.currency}{unit}")
            if item.get("price_note"):
                parts.append(f"({item.get('price_note')})")
            if item.get("bedrooms"):
                parts.append(f"; {item.get('bedrooms')} bed")
            if item.get("features"):
                parts.append(f"; {item.get('features')}")
            lines.append("- " + " ".join(part for part in parts if part))
        if len(lines) == 1:
            lines.append("- (no listings added yet — collect the caller's needs; an agent will call back with options)")
        availability = visit_availability(ctx)
        if availability:
            lines.append(f"Viewings: {schedule_phrase(availability, 'en', ctx)}.")
        return lines

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.direction == DIRECTION_INBOUND:
            lines.append(
                f"Caller's number: {ctx.caller_number}." if ctx.caller_number else "Caller's number is unknown — the system will ask for it."
            )
        else:
            details = ctx.record_details()
            known = ", ".join(f"{key}: {value}" for key, value in details.items() if key != "lead_score" and value not in (None, ""))
            lines.append(f"This is a follow-up call to a lead: {self.person_name(ctx)}. Known so far: {known or 'nothing yet'}.")
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [str(item.get("location", "")) for item in ctx.items(KIND_PROPERTY)][:8]
        if normalize_language(ctx.merchant_value("language", "en")) == "bn":
            hints += ["কাঠা", "শতাংশ", "বিঘা", "ফ্ল্যাট", "প্লট", "লাখ", "কোটি", "সাইট ভিজিট"]
        return hints

    # ---- prefetch / preview ------------------------------------------------------------
    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        keys = (
            "intent", "caller_name", "property_type", "location", "location_sell", "budget", "budget_rent", "size",
            "asking_price", "timeline", "timeline_rent", "phone", "closing_lead", "closing_not_interested",
        )
        lines = super().prefetch_lines(ctx, lang) + [lang_text(_LINES[key], lang) for key in keys]
        lines += [phrase("amend_question", lang), phrase("phone_invalid", lang), phrase("closing_inquiry", lang)]
        availability = visit_availability(ctx)
        if availability:
            lines.append(lang_text(_LINES["visit_date"], lang).format(schedule=schedule_phrase(availability, lang, ctx)))
        return lines

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        if ctx.direction == DIRECTION_INBOUND:
            if lang == "bn":
                return [
                    f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                    "চাহিদা: কেনা/ভাড়া/বিক্রি, নাম, প্রপার্টির ধরন, এলাকা, বাজেট, কবে নিতে চান।",
                    "প্রপার্টি: আপনার তালিকা থেকে মিলে যাওয়া সর্বোচ্চ দুটি প্রপার্টি বলে।",
                    "সাইট ভিজিট: দিন ঠিক করে পড়ে শোনায়, 'হ্যাঁ' বললে বুক হয়।",
                    "লিড: সবার তথ্য লিড হিসেবে জমা হয়, হট/ওয়ার্ম/কোল্ড স্কোরসহ। দাম বা দলিল নিয়ে কোনো প্রতিশ্রুতি দেয় না।",
                ]
            return [
                f"Greeting: \"{self.opening(ctx, lang)}\"",
                "Needs: buy / rent / sell, name, property type, area, budget, timeline.",
                "Listings: presents at most two fitting listings from your list.",
                "Site visit: picks a day, reads it back, books on a 'yes'.",
                "Lead: every caller is saved as a lead scored hot / warm / cold. Never promises prices or legal status.",
            ]
        if lang == "bn":
            return [
                f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                "ফলো-আপ: আগের আগ্রহ মনে করিয়ে জিজ্ঞেস করে এখনও আগ্রহী কি না।",
                "আগ্রহী হলে: বাকি তথ্য নিয়ে প্রপার্টি বলে সাইট ভিজিট বুক করে।",
            ]
        return [
            f"Greeting: \"{self.opening(ctx, lang)}\"",
            "Follow-up: reminds them of their enquiry and asks if they are still interested.",
            "If yes: fills in missing details, presents listings and books a site visit.",
        ]


INBOUND = RealEstateFlow(DIRECTION_INBOUND)
OUTBOUND = RealEstateFlow("outbound")


def _summary(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    score = details.get("lead_score") if isinstance(details, dict) else ""
    base = str(getattr(record, "items_summary", "") or "")
    listing = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    return " · ".join(part for part in (base, listing, str(score or "").upper()) if part)


REAL_ESTATE = Vertical(
    key="real_estate",
    label=L("Real estate / land broker", "রিয়েল এস্টেট / জমির ব্রোকার"),
    description=L(
        "Answers buyers, renters and sellers: qualifies them, presents matching listings, books site visits and scores every lead; follows up leads by phone.",
        "ক্রেতা, ভাড়াটিয়া ও বিক্রেতার ফোন ধরে: চাহিদা জেনে মিলে যাওয়া প্রপার্টি বলে, সাইট ভিজিট বুক করে, প্রতিটি লিড স্কোর করে; লিড ফলো-আপ কলও করে।",
    ),
    record_kind=KIND_LEAD,
    record_label=L("Lead", "লিড"),
    record_label_plural=L("Leads", "লিড"),
    record_fields=(
        FieldSpec("customer_name", L("Name", "নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec(
            "intent",
            L("Looking to", "উদ্দেশ্য"),
            "select",
            options=(("buy", L("Buy", "কেনা")), ("rent", L("Rent", "ভাড়া")), ("sell", L("Sell", "বিক্রি"))),
            default="buy",
        ),
        FieldSpec(
            "property_type",
            L("Property type", "ধরন"),
            "select",
            options=tuple((key, L(words["en"].capitalize(), words["bn"])) for key, words in _TYPE_WORDS.items()),
        ),
        FieldSpec("location", L("Area", "এলাকা"), placeholder="Riverside / Downtown"),
        FieldSpec("budget", L("Budget", "বাজেট"), placeholder="400k–450k"),
        FieldSpec("catalog_item_id", L("Listing of interest", "আগ্রহের প্রপার্টি"), "catalog"),
        FieldSpec("scheduled_at", L("Site visit", "সাইট ভিজিট"), "datetime", list_column=True),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_PROPERTY,
    catalog_label=L("Listing", "প্রপার্টি"),
    catalog_label_plural=L("Listings", "প্রপার্টি তালিকা"),
    catalog_fields=(
        FieldSpec("name", L("Title", "শিরোনাম"), required=True, placeholder="3-bed apartment, Riverside Towers"),
        FieldSpec(
            "listing_type",
            L("For", "উদ্দেশ্য"),
            "select",
            required=True,
            options=(("sale", L("Sale", "বিক্রি")), ("rent", L("Rent", "ভাড়া"))),
            default="sale",
        ),
        FieldSpec(
            "property_type",
            L("Type", "ধরন"),
            "select",
            required=True,
            options=tuple((key, L(words["en"].capitalize(), words["bn"])) for key, words in _TYPE_WORDS.items()),
            default="land",
        ),
        FieldSpec("location", L("Area", "এলাকা"), required=True, placeholder="Riverside"),
        FieldSpec("size", L("Size", "আকার"), placeholder="1,450 sq ft / 0.5 acre / 5 katha"),
        FieldSpec("price", L("Price (monthly for rent)", "দাম (ভাড়া হলে মাসিক)"), "money"),
        FieldSpec("price_note", L("Price note", "দামের নোট"), placeholder="negotiable / per katha"),
        FieldSpec("bedrooms", L("Bedrooms", "বেডরুম"), "number"),
        FieldSpec("features", L("Highlights", "বৈশিষ্ট্য"), "textarea", placeholder="South facing, parking, ready to move in"),
    ),
    config_fields=(
        FieldSpec("visit_days", L("Viewing days", "সাইট ভিজিটের দিন"), "days", default=["mon", "tue", "wed", "thu", "fri", "sat"]),
        FieldSpec("visit_start", L("Visits from", "ভিজিট শুরু"), "time", default="10:00"),
        FieldSpec("visit_end", L("Visits until", "ভিজিট শেষ"), "time", default="18:00"),
        FieldSpec("visit_slot_minutes", L("Minutes per visit", "প্রতি ভিজিট (মিনিট)"), "number", default=60),
        FieldSpec("visit_capacity", L("Visits at the same time", "একসাথে কয়টি ভিজিট"), "number", default=1),
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=14),
    ),
    config_defaults={
        "visit_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        "visit_start": "10:00",
        "visit_end": "18:00",
        "visit_slot_minutes": 60,
        "visit_capacity": 1,
        "booking_horizon_days": 14,
        "lead_minutes": 120,
    },
    status_labels={
        "pending": L("New", "নতুন"),
        "confirmed": L("Visit booked", "ভিজিট বুকড"),
        "cancelled": L("Not interested", "আগ্রহী নন"),
        "needs_review": L("Follow up", "ফলো-আপ"),
    },
    flows={"inbound": INBOUND, "outbound": OUTBOUND},
    outbound_label=L("Follow-up call", "ফলো-আপ কল"),
    scheduled=True,
    summarize=_summary,
)

__all__ = ["REAL_ESTATE", "RealEstateFlow", "lead_score", "visit_availability"]
