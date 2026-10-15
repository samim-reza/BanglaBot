"""Find the caller's existing record (appointment, booking, order) by their phone number."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.flows.base import STAGE_DONE
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.common import join_and

DescribeFn = Callable[[Any, CallContext, str], str]


class LookupSkill(Skill):
    key = "lookup"
    label = L2("Find their booking", "বুকিং খোঁজা")
    description = L2("Finds the caller's booking by phone number.", "ফোন নম্বর দিয়ে কলারের বুকিং খোঁজে।")
    toggleable = False
    lines = (
        line("which", "This number has {list} — which one do you mean?", "এই নম্বরে {list} আছে — কোনটার কথা বলছেন?", label="Ask which one", variables=("list",)),
        line("none", "Sorry, I can't find a booking for this number. Would you like to make a new one?", "দুঃখিত, এই নম্বরে কোনো বুকিং খুঁজে পাচ্ছি না। নতুন বুকিং করতে চান?", label="Nothing found", static=True),
    )
    goal = "Find out which of the caller's bookings they mean."

    def __init__(
        self,
        key: str | None = None,
        *,
        record_kind: str,
        describe: DescribeFn,
        slot: str = "record",
        which_stage: str = "which_record",
        none_stage: str = "no_record_found",
        new_branch: str = "book",
        prefix: str = "A",
        noun: str = "booking",
        **overrides: Any,
    ) -> None:
        super().__init__(key, **overrides)
        self.record_kind = record_kind
        self.describe = describe
        self.slot = slot
        self.which_stage = which_stage
        self.none_stage = none_stage
        self.new_branch = new_branch
        self.prefix = prefix
        self.slots = (
            SlotSpec(slot, f"Which existing {noun} (ref {prefix}1, {prefix}2, … from the caller's list).", directions=("inbound",)),
            SlotSpec("book_instead", f"No {noun} was found: true = they want a new one, false = no.", {"type": "boolean"}, directions=("inbound",)),
        )
        self.yes_no = {none_stage: "book_instead"}
        self.stage_slots = {which_stage: (slot,), none_stage: ("book_instead",)}

    def records(self, ctx: CallContext) -> list[Any]:
        return [
            record
            for record in ctx.caller_records
            if str(getattr(record, "kind", "") or "") == self.record_kind and isinstance(getattr(record, "scheduled_at", None), datetime)
        ]

    def target(self, slots: dict[str, Any], ctx: CallContext) -> Any | None:
        wanted = str(slots.get(self.slot) or "")
        for index, record in enumerate(self.records(ctx), start=1):
            if wanted in (f"{self.prefix}{index}", str(getattr(record, "id", ""))):
                return record
        return None

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return (self.which_stage, self.none_stage)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if not self.records(ctx):
            if slots.get("book_instead") is None:
                return self.none_stage
            return STAGE_DONE  # "no" to a new booking: nothing more to do (a "yes" re-routes in on_saved)
        if not slots.get(self.slot):
            return self.which_stage
        return None

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        if self.slot in fields:
            wanted = str(fields[self.slot]).strip().upper()
            if wanted not in {f"{self.prefix}{i}" for i in range(1, len(self.records(ctx)) + 1)}:
                fields.pop(self.slot)
            else:
                fields[self.slot] = wanted
        return fields, None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if saved.get("book_instead") is True:
            slots["intent"] = self.new_branch

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        if not slots.get(self.slot) and len(self.records(ctx)) == 1:
            slots[self.slot] = f"{self.prefix}1"

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if stage == self.none_stage:
            return b.text("none", language)
        items = [self.describe(record, ctx, language) for record in self.records(ctx)[:3]]
        return b.text("which", language, list=join_and(items, language))

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("none", language)]


__all__ = ["LookupSkill"]
