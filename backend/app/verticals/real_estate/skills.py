"""Real-estate skills: buy / rent / sell, the caller's needs, the listing pitch, the follow-up
question, and the read-back / closing wording."""

from __future__ import annotations

from typing import Any

from app.flows.base import STAGE_COMMIT, Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, LineSpec, Skill, lang_pick
from app.skills.library.intent import IntentSkill
from app.skills.library.lines import L, line
from app.verticals.real_estate.catalog import KIND_PROPERTY, interest_phrase, listing_facts, matching_listings, number

_PITCH_GUIDE = {
    "en": (
        "Now tell the caller, in one or two short sentences, about at most two listings that fit their needs (type, area, budget) — "
        "area, size and price in words — then ask whether they'd like a site visit. If nothing fits, say so honestly and ask whether "
        "an agent may call with other options (then wants_visit=false). When the caller picks a listing, save property=<ref>."
    ),
}


class LeadIntentSkill(IntentSkill):
    """The buy / rent / sell router — also on follow-up calls (a lead may not have said yet)."""

    def __init__(self, choices: dict[str, str], **overrides: Any) -> None:
        super().__init__(choices, **overrides)
        self.slots = (SlotSpec("intent", "What the caller wants.", {"type": "string", "enum": list(self.choices)}),)


class NeedSkill(Skill):
    """One question about what the caller wants (or sells); done once any of its slots is known.

    A line ``<key>_<intent>`` (``budget_rent``, ``location_sell``) replaces the default for that intent."""

    def __init__(self, key: str, *, slots: tuple[SlotSpec, ...], lines: tuple[LineSpec, ...], long: bool = False, **overrides: Any) -> None:
        super().__init__(key, slots=slots, lines=lines, **overrides)
        self.stage_slots = {key: tuple(spec.key for spec in slots)}
        self.volunteerable = frozenset(spec.key for spec in slots)
        self.long_answer = frozenset({key}) if long else frozenset()

    def required(self, b: BoundSkill) -> tuple[str, ...]:
        return (self.key,)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return None if any(slots.get(spec.key) not in (None, "") for spec in self.slots) else self.key

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        for spec in self.slots:
            if spec.schema.get("type") == "number" and spec.key in fields and number(fields[spec.key]) is None:
                fields.pop(spec.key)
        return fields, None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        variant = f"{self.key}_{slots.get('intent') or ''}"
        return b.text(variant if self.line_spec(variant) else self.key, language)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text(spec.key, language) for spec in self.lines]


class PitchSkill(Skill):
    """At most two fitting listings, in the model's words, then: would they like a site visit?"""

    key = "listings"
    kind = "gate"
    label = L("Matching listings")
    description = L("Presents up to two listings that fit and offers a site visit.")
    toggleable = False
    slots = (
        SlotSpec("property", "The listing the caller is interested in (ref P1, P2, …)."),
        SlotSpec("wants_visit", "true = they want a site visit; false = no visit now (an agent calls back).", {"type": "boolean"}),
    )
    yes_no = {"listings": "wants_visit"}
    stage_slots = {"listings": ("property", "wants_visit")}
    volunteerable = frozenset({"property", "wants_visit"})
    goal = "Present at most two fitting listings and ask about a site visit (see the instruction)."

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("listings",)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return "listings" if slots.get("wants_visit") is None else None

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        if "property" in fields:
            found = ctx.find_items(fields["property"], KIND_PROPERTY, fields=("location",))
            if len(found) == 1:
                fields["property"] = found[0].ref
            else:
                fields.pop("property")
        return fields, None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if saved.get("visit_date") or saved.get("visit_time_pref"):
            slots["wants_visit"] = True  # naming a day is a yes to the visit

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        """A listing the caller named answers the type / area questions."""
        found = ctx.find_items(slots.get("property"), KIND_PROPERTY) if slots.get("property") else []
        if len(found) != 1:
            return
        listing = found[0]
        for key, value in (("property_type", listing.get("property_type")), ("location", listing.get("location"))):
            if value and slots.get(key) in (None, ""):
                slots[key] = value


    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction:
        refs = ", ".join(item.ref for item in matching_listings(slots, ctx)) or "none"
        return Instruction("listings", f"{lang_pick(_PITCH_GUIDE, language)} (Listings that may fit: {refs})")

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return listing_facts(ctx)


class InterestedSkill(Skill):
    """Follow-up calls: still interested? A no ends the call as *not interested* (no read-back)."""

    key = "interested"
    kind = "gate"
    label = L("Still interested?")
    toggleable = False
    slots = (SlotSpec("still_interested", "Follow-up call: true = still interested, false = not interested any more.", {"type": "boolean"}, directions=("outbound",)),)
    gated = ("still_interested",)
    yes_no = {"still_interested": "still_interested"}
    lines = (
        line(
            "still_interested",
            "You had asked us about {interest}. Are you still interested?",
            label="Follow-up question",
            variables=("interest",),
        ),
    )
    goal = "Are they still interested?"

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        interested = slots.get("still_interested")
        if interested is None:
            return "still_interested"
        return STAGE_COMMIT if interested is False else None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("still_interested", language, interest=interest_phrase(slots, ctx, language))


class RealtyConfirmSkill(Skill):
    """Holds the read-back and closing wording (editable); the flow assembles them."""

    key = "confirm"
    kind = "line"
    toggleable = False
    label = L("Read-back and closing")
    description = L("What is read back before booking a viewing or passing a lead on, and what is said after.")
    lines = (
        line(
            "readback_visit",
            "So, {name}, a viewing of {what} {when} — our agent will call the day before with the meeting point.",
            label="Read-back (viewing)",
            variables=("name", "what", "when"),
        ),
        line("confirm_visit", "Shall I confirm it?", label="Confirm question (viewing)", static=True),
        line(
            "readback_sell",
            "So your {type} in {area}, {size}, asking {price}. Our agent will get in touch with you — is that right?",
            label="Read-back (seller)",
            variables=("type", "area", "size", "price"),
        ),
        line("closing_visit", "Your viewing is confirmed — {when}. Our agent will call you the day before.", label="After booking a viewing", variables=("when",)),
        line("closing_lead", "One of our agents will call you shortly with more options.", label="Buyer / renter lead", static=True),
        line("closing_seller", "One of our agents will call you shortly about a valuation and selling your property.", label="Seller lead", static=True),
        line("closing_not_interested", "Alright, no problem. Call us any time you need.", label="Not interested any more", static=True),
        line("knows_person", "{name} had asked us about a property. Do you know them?", label="Someone else answered", variables=("name",)),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text(key, language) for key in ("closing_lead", "closing_seller", "closing_not_interested")]


__all__ = ["InterestedSkill", "LeadIntentSkill", "NeedSkill", "PitchSkill", "RealtyConfirmSkill"]
