"""Salon skills: which service, who does it ("anyone" allowed), the day (duration-aware), and the
read-back / closing wording."""

from __future__ import annotations

from typing import Any

from app.flows.base import Instruction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L, line
from app.skills.library.schedule import ScheduleSkill
from app.verticals.common import NOTICE, join_and, schedule_phrase
from app.verticals.salon.catalog import (
    ANY,
    KIND_SERVICE,
    KIND_STAFF,
    chosen_service,
    offers,
    service_facts,
    services_phrase,
    staff_by_ref,
    staff_facts,
    staff_for,
    staff_phrase,
)

ANY_WORDS = ("any", "anyone", "anybody", "no preference", "whoever", "doesn't matter", "first available")


class SalonServiceSkill(Skill):
    key = "service"
    label = L("Service")
    description = L("Finds the service the caller wants on your list.")
    toggleable = False
    slots = (SlotSpec("service", "The service, as the ref from the service list (S1, S2, …) — or its name if unsure.", directions=("inbound",)),)
    volunteerable = frozenset({"service"})
    lines = (
        line("service", "What would you like to book? We do {services}.", label="Ask for the service", variables=("services",)),
        line("choose", "Which one — {names}?", label="Several match", variables=("names",)),
        line("unknown", "Sorry, we don't offer that. We do {services}. What would you like?", label="Not offered", variables=("services",)),
    )
    goal = "Which service do they want (save the S-ref)?"

    def initial(self, b: BoundSkill, ctx: CallContext) -> dict[str, Any]:
        services = ctx.items(KIND_SERVICE)
        return {"service": services[0].ref} if ctx.direction == DIRECTION_INBOUND and len(services) == 1 else {}

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        found = ctx.find_items(fields["service"], KIND_SERVICE, fields=("category",))
        if len(found) == 1:
            fields["service"] = found[0].ref
            return fields, None
        fields.pop("service")
        if found:
            return fields, Instruction("service", b.text("choose", language, names=join_and([item.name for item in found[:4]], language)), verbatim=True)
        return fields, Instruction("service", b.text("unknown", language, services=services_phrase(ctx, language)), verbatim=True)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("service", language, services=services_phrase(ctx, language))

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return service_facts(ctx)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("service", language, services=services_phrase(ctx, language))]


class StaffSkill(Skill):
    """Who does it. Skipped when only one person offers the service (or there is no staff list)."""

    key = "staff"
    label = L("Stylist / therapist")
    description = L("Asks who they'd like — or anyone available.")
    slots = (SlotSpec("staff", "Who the caller wants (ref T1, T2, … from the staff list), or 'any' when they have no preference."),)
    volunteerable = frozenset({"staff"})
    lines = (
        line("staff", "Do you have someone in mind — {names} — or is anyone fine?", label="Ask who", variables=("names",)),
        line("not_offered", "Sorry, {name} doesn't do {service}. {names} can — or is anyone fine?", label="They don't do that service", variables=("name", "service", "names")),
        line("choose", "We have {names} — who would you like?", label="Several match", variables=("names",)),
        line("unknown", "Sorry, I can't find that name. We have {names} — or is anyone fine?", label="No match", variables=("names",)),
    )
    goal = "Who would they like (save the T-ref), or 'any' if anyone is fine?"

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        service = chosen_service(slots, ctx)
        if service is None:
            return
        capable = staff_for(service, ctx)
        current = slots.get("staff")
        if current and current != ANY and current not in {person.ref for person in capable}:
            slots.pop("staff")  # a changed service someone else does
            current = None
        if not current and (not ctx.items(KIND_STAFF) or len(capable) <= 1):
            slots["staff"] = capable[0].ref if capable else ANY

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        value = " ".join(str(fields["staff"]).split())
        if value.lower() in ANY_WORDS:
            fields["staff"] = ANY
            return fields, None
        found = ctx.find_items(value, KIND_STAFF)
        service = chosen_service(slots, ctx)
        capable = staff_for(service, ctx)
        names = staff_phrase(capable, language)
        if len(found) == 1 and (service is None or offers(found[0], service)):
            fields["staff"] = found[0].ref
            return fields, None
        fields.pop("staff")
        if len(found) == 1 and service is not None:
            text = b.text("not_offered", language, name=found[0].name, service=service.name, names=names)
        elif found:
            text = b.text("choose", language, names=staff_phrase(found, language))
        else:
            text = b.text("unknown", language, names=names)
        return fields, Instruction("staff", text, verbatim=True)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("staff", language, names=staff_phrase(staff_for(chosen_service(slots, ctx), ctx), language))

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return staff_facts(ctx)


class SalonScheduleSkill(ScheduleSkill):
    """The day: the chosen person's working days, or just "which day" when anyone will do."""

    who_notice = "closed_day_person"

    def __init__(self, key: str | None = None, **kwargs: Any) -> None:
        # A day the chosen stylist is off is about them, not the salon ("Maya isn't in on Monday").
        kwargs.setdefault("notice_who", _chosen_staff_name)
        super().__init__(key, **kwargs)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if slots.get(NOTICE):
            return b.text("ask_short", language)
        person = staff_by_ref(slots.get("staff"), ctx)
        availability = self.availability(slots, ctx) if person is not None else None
        if availability is None:
            return b.text("ask_any", language)
        return b.text("ask", language, who=person.name, schedule=schedule_phrase(availability, language, ctx))

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask_short", language), b.text("ask_any", language)]


def _chosen_staff_name(slots: dict[str, Any], ctx: CallContext, language: str) -> str:
    person = staff_by_ref(slots.get("staff"), ctx)
    return person.name if person is not None else ""


class SalonConfirmSkill(Skill):
    """Holds the read-back and closing wording (editable); the flow assembles them."""

    key = "confirm"
    kind = "line"
    toggleable = False
    label = L("Read-back and closing")
    description = L("What is read back before booking, and what is said after.")
    lines = (
        line("readback_book", "So that's {service} with {staff}, {when}. {price_part}", label="Read-back (new)", variables=("service", "staff", "when", "price_part", "minutes")),
        line("readback_book_any", "So that's {service}, {when}. {price_part}", label="Read-back (no staff list)", variables=("service", "when", "price_part", "minutes")),
        line("price_part", "It's {price}.", label="Price", variables=("price",)),
        line("confirm_book", "Shall I book it?", label="Confirm question (new)", static=True),
        line("readback_reschedule", "So I'll move your {service} with {staff} to {when}.", label="Read-back (move)", variables=("service", "staff", "when")),
        line("confirm_reschedule", "Is that right?", label="Confirm question (move)", static=True),
        line("readback_cancel", "Shall I cancel your {service} with {staff}, {when}?", label="Read-back (cancel)", variables=("service", "staff", "when")),
        line("closing_booked", "You're all set — {service} with {staff}, {when}.", label="After booking", variables=("service", "staff", "when")),
        line("closing_rescheduled", "Your booking is now {when}.", label="After moving", variables=("when",)),
        line("closing_cancelled", "Alright, your booking has been cancelled.", label="After cancelling", static=True),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("closing_cancelled", language), b.text("confirm_book", language)]


__all__ = ["ANY_WORDS", "SalonConfirmSkill", "SalonScheduleSkill", "SalonServiceSkill", "StaffSkill"]
