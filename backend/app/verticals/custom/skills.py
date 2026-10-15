"""Custom engine skills: which bookable thing, and the read-back / closing wording (owner-editable)."""

from __future__ import annotations

from typing import Any

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.custom.catalog import KIND_RESOURCE, names, resource_facts, resources


class ResourceSkill(Skill):
    key = "resource"
    toggleable = False
    label = L2("What to book", "কী বুক করবেন")
    description = L2("Finds what they want to book from your list.", "আপনার তালিকা থেকে কী বুক করবেন তা খোঁজে।")
    slots = (SlotSpec("resource", "What they want to book, as the ref from the list (I1, I2, …) — or its name if unsure."),)
    volunteerable = frozenset({"resource"})
    lines = (
        line("resource", "What would you like to book? We have {names}.", "কী বুক করতে চান? আমাদের আছে {names}।", label="Ask what to book", variables=("names",)),
        line("choose", "We have {names} — which one would you like?", "আমাদের আছে {names} — কোনটা চান?", label="Several match", variables=("names",)),
        line("unknown", "Sorry, I can't find that. We have {names}. Which would you like?", "দুঃখিত, এটা পাচ্ছি না। আমাদের আছে {names}। কোনটা চান?", label="No match", variables=("names",)),
    )
    goal = "Find out what they want to book (save the ref)."

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return slots.get("intent") == "book"

    def initial(self, b: BoundSkill, ctx: CallContext) -> dict[str, Any]:
        items = resources(ctx)
        return {"resource": items[0].ref} if len(items) == 1 else {}

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        if slots.get("intent") == "book" and not resources(ctx):
            slots["intent"] = "message"  # nothing bookable yet: take a message instead

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        matches = ctx.find_items(fields["resource"], KIND_RESOURCE, fields=("description",))
        if len(matches) == 1:
            fields["resource"] = matches[0].ref
            return fields, None
        fields.pop("resource")
        if matches:
            return fields, Instruction("resource", b.text("choose", language, names=names(ctx, language, matches[:4])), verbatim=True)
        return fields, Instruction("resource", b.text("unknown", language, names=names(ctx, language)), verbatim=True)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("resource", language, names=names(ctx, language))

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return resource_facts(ctx)


class CustomConfirmSkill(Skill):
    key = "confirm"
    kind = "line"
    toggleable = False
    label = L2("Read-back and closing", "পড়ে শোনানো ও সমাপ্তি")
    description = L2("What is read back before saving, and what is said after.", "সেভ করার আগে যা পড়ে শোনানো হয় ও পরে যা বলা হয়।")
    lines = (
        line("readback_book", "So that's {resource} for {name}, {when}.", "তাহলে {name} এর জন্য {when} {resource}।", label="Booking read-back", variables=("resource", "name", "when")),
        line("confirm_book", "Shall I book it?", "বুক করব?", label="Confirm question (booking)", static=True),
        line("readback_inquiry", "So I'll pass your details to our team: {details}. They'll get back to you on {phone}.", "তাহলে আপনার তথ্য আমাদের টিমকে দিচ্ছি: {details}। তারা {phone} নম্বরে যোগাযোগ করবে।", label="Inquiry read-back", variables=("details", "phone")),
        line("readback_message", "So I'll pass this on to our team: {message}. They'll call you back on {phone}.", "তাহলে আমাদের টিমকে জানাচ্ছি: {message}। তারা {phone} নম্বরে ফোন করবে।", label="Message read-back", variables=("message", "phone")),
        line("confirm_lead", "Is that right?", "ঠিক আছে?", label="Confirm question (inquiry / message)", static=True),
        line("closing_booked", "You're booked for {when}.", "আপনার বুকিং হয়েছে — {when}।", label="After booking", variables=("when",)),
        line("closing_lead", "Thanks — our team will get back to you soon.", "ধন্যবাদ — আমাদের টিম শীঘ্রই যোগাযোগ করবে।", label="After an inquiry / message", static=True),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("confirm_book", language), b.text("confirm_lead", language), b.text("closing_lead", language)]


__all__ = ["CustomConfirmSkill", "ResourceSkill"]
