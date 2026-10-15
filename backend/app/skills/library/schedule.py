"""Agree a day and time — the backend proposes the free slot nearest the caller's preference."""

from __future__ import annotations

from typing import Any, Callable

from app.flows.context import CallContext
from app.flows.scheduling import Availability
from app.flows.steps import SlotSpec
from app.flows.timefmt import calendar_facts
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line
from app.verticals.common import NOTICE, plan_booking, schedule_phrase

AvailabilityFn = Callable[[dict[str, Any], CallContext], "Availability | None"]
WhoFn = Callable[[dict[str, Any], CallContext, str], str]


class ScheduleSkill(Skill):
    key = "schedule"
    label = L2("Day and time", "দিন ও সময়")
    description = L2("Checks the schedule and offers the nearest free time.", "সময়সূচি দেখে কাছের খালি সময় দেয়।")
    lines = (
        line("ask", "{who} is available {schedule}. Which day would you like?", "{who} {schedule} পাওয়া যায়। কোন দিন চান?", label="Ask for a day", variables=("who", "schedule")),
        line("ask_short", "Which day would you like?", "কোন দিন চান?", label="Ask again", static=True),
    )
    date_slots = ("date",)
    volunteerable = frozenset({"date", "time_pref"})
    goal = "Get the day they want (and a preferred time if they mention one)."

    def __init__(
        self,
        key: str | None = None,
        *,
        availability: AvailabilityFn,
        who: WhoFn | None = None,
        needed: Callable[[dict[str, Any], CallContext], bool] | None = None,
        date_key: str = "date",
        pref_key: str = "time_pref",
        window_key: str = "",
        notice_who: WhoFn | None = None,
        **overrides: Any,
    ) -> None:
        super().__init__(key, **overrides)
        self.availability = availability
        self.who = who or (lambda slots, ctx, lang: "")
        self.notice_who = notice_who
        self.needed = needed or (lambda slots, ctx: True)
        self.date_key = date_key
        self.pref_key = pref_key
        self.window_key = window_key
        self.date_slots = (date_key,)
        # The step saves the day plus whichever preference slots exist (a time, or a named window).
        extra = tuple(dict.fromkeys(key for key in (pref_key, window_key) if key))
        self.stage_slots = {date_key: (date_key, *extra)}
        if "volunteerable" not in overrides:
            self.volunteerable = frozenset({date_key, *extra})
        if not overrides.get("slots"):
            specs = [SlotSpec(date_key, "Date as YYYY-MM-DD. Convert a day the caller names ('tomorrow', 'Wednesday', 'next Monday') with the calendar in the facts.")]
            if pref_key:
                specs.append(SlotSpec(pref_key, "Preferred time: HH:MM (24 h) or morning / afternoon / evening. Only if the caller said one."))
            self.slots = tuple(specs)

    def required(self, b: BoundSkill) -> tuple[str, ...]:
        return (self.date_key,)

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return self.needed(slots, ctx)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if not slots.get(self.date_key) or not slots.get("slot"):
            return self.date_key
        return None

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        if not self.needed(slots, ctx):
            for key in ("slot", "serial", "window"):
                slots.pop(key, None)
            return
        who = self.notice_who(slots, ctx, "bn") if self.notice_who else ""
        plan_booking(
            slots,
            ctx,
            self.availability(slots, ctx),
            date_key=self.date_key,
            pref_key=self.pref_key,
            window_key=self.window_key,
            who=who,
        )

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if slots.get(NOTICE):
            return b.text("ask_short", language)  # the notice already said which days work
        availability = self.availability(slots, ctx)
        schedule = schedule_phrase(availability, language, ctx) if availability else ""
        return b.text("ask", language, who=self.who(slots, ctx, language), schedule=schedule)

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask_short", language)]


__all__ = ["ScheduleSkill"]
