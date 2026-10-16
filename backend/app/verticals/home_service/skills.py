"""Home-service skills: which service, the problem, the job address (with the service-area check),
the visit-confirmation questions, and the read-back / closing wording."""

from __future__ import annotations

from typing import Any

from app.flows.base import Instruction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import CONFIRMED, SlotSpec
from app.skills.base import BoundSkill, Skill
from app.skills.library.intent import IntentSkill
from app.skills.library.lines import L, line
from app.verticals.common import join_and
from app.verticals.home_service.catalog import (
    KIND_SERVICE,
    area_facts,
    area_ok,
    chosen_service,
    record_when,
    service_areas,
    service_facts,
    services_phrase,
)


class BookFirstIntentSkill(IntentSkill):
    """The router, pre-set to *book*: a caller is only routed elsewhere when they ask to move or cancel."""

    def initial(self, b: BoundSkill, ctx: CallContext) -> dict[str, Any]:
        return {"intent": "book"} if ctx.direction == DIRECTION_INBOUND else {}


class ServiceSkill(Skill):
    key = "service"
    label = L("Service")
    description = L("Matches the caller's job to a service on your list.")
    toggleable = False
    slots = (SlotSpec("service", "The service, as the ref from the service list (S1, S2, …) — or its name if unsure.", directions=("inbound",)),)
    stage_slots = {"service": ("service", "problem")}
    volunteerable = frozenset({"service"})
    lines = (
        line("service", "Which service do you need? We do {services}.", label="Ask for the service", variables=("services",)),
        line("choose", "Which one — {names}?", label="Several match", variables=("names",)),
    )
    goal = "Which service do they need (map their problem to a service ref)?"

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
            text = b.text("choose", language, names=join_and([item.name for item in found[:4]], language))
        else:
            text = b.text("service", language, services=services_phrase(ctx, language))
        return fields, Instruction("service", text, verbatim=True)

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("service", language, services=services_phrase(ctx, language))

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return service_facts(ctx)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("service", language, services=services_phrase(ctx, language))]


class ProblemSkill(Skill):
    key = "problem"
    label = L("The problem")
    description = L("A short description of the job.")
    slots = (SlotSpec("problem", "The problem in the caller's words, short (e.g. 'AC leaking water', 'kitchen sink blocked').", directions=("inbound",)),)
    lines = (line("problem", "Could you briefly describe the problem?", label="Ask about the problem", static=True),)
    long_answer = frozenset({"problem"})
    volunteerable = frozenset({"problem"})
    goal = "A short description of the problem."

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("problem", language)]


class AddressSkill(Skill):
    """The job address; only the locality is checked against the service areas — a free-form
    address in another script would never match reliably, and a wrong "we don't cover you" loses a job."""

    key = "address"
    label = L("Job address")
    description = L("Takes the address and checks it is inside your service areas.")
    toggleable = False
    slots = (
        SlotSpec("address", "Full job address as said (area, road, house, floor, landmark)."),
        SlotSpec("area", "Locality / neighbourhood of the address (e.g. Midtown, Westside). If it is one of the service areas in the facts, spell it exactly as listed."),
    )
    stage_slots = {"address": ("address", "area")}
    long_answer = frozenset({"address"})
    volunteerable = frozenset({"address", "area"})
    lines = (
        line("address", "What's the address for the job — area, road and house number?", label="Ask for the address", static=True),
        line(
            "out_of_area",
            "Sorry, we don't cover that area yet — we work in {areas}. Tell me if the job is at an address there.",
            label="Outside the service area",
            variables=("areas",),
        ),
    )
    goal = "The job address (save address and area)."

    def required(self, b: BoundSkill) -> tuple[str, ...]:
        return ("address",)

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        if fields.get("area") and not area_ok(fields.get("area"), ctx):
            fields.pop("area", None)
            fields.pop("address", None)
            areas = join_and(service_areas(ctx)[:6], language)
            return fields, Instruction("address", b.text("out_of_area", language, areas=areas), verbatim=True)
        return fields, None

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return area_facts(ctx)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("address", language)]


class TimeOkSkill(Skill):
    key = "time_ok"
    kind = "gate"
    label = L("Is the time OK?")
    toggleable = False
    slots = (SlotSpec("time_ok", "Confirmation call: true = the booked time works, false = it doesn't.", {"type": "boolean"}, directions=("outbound",)),)
    gated = ("time_ok",)
    yes_no = {"time_ok": "time_ok"}
    lines = (
        line(
            "time_ok",
            "Our technician is coming {when} for your {service}. Does that time still work?",
            label="Confirmation question",
            variables=("when", "service"),
        ),
    )
    goal = "Does the booked visit time still work?"

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("time_ok",)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return "time_ok" if slots.get("time_ok") is None else None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if saved.get("time_ok") is True:
            slots[CONFIRMED] = True

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        service = chosen_service(slots, ctx)
        return b.text("time_ok", language, when=record_when(ctx.record, ctx, language), service=service.name if service else "")


class AnotherDaySkill(Skill):
    key = "new_time"
    kind = "gate"
    label = L("Another day?")
    toggleable = False
    slots = (SlotSpec("wants_new_time", "After the time doesn't work: true = another day, false = cancel the booking.", {"type": "boolean"}, directions=("outbound",)),)
    yes_no = {"wants_new_time": "wants_new_time"}
    lines = (line("new_time", "Alright. Shall we come on another day instead?", label="Offer another day", static=True),)
    goal = "Another day, or cancel?"

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return slots.get("time_ok") is False

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return ("wants_new_time",)

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        return "wants_new_time" if slots.get("wants_new_time") is None else None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        if saved.get("wants_new_time") is False:
            slots[CONFIRMED] = True  # "doesn't work" + "no other day": cancel without another read-back

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("new_time", language)

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("new_time", language)]


class HomeConfirmSkill(Skill):
    """Holds the read-back and closing wording (editable); the flow assembles them."""

    key = "confirm"
    kind = "line"
    toggleable = False
    label = L("Read-back and closing")
    description = L("What is read back before booking, and what is said after.")
    lines = (
        line("readback_book", "So a technician will come to {address} {when} for {service}. {price}", label="Read-back (new)", variables=("address", "when", "service", "price")),
        line("confirm_book", "Shall I confirm the booking?", label="Confirm question (new)", static=True),
        line("readback_move", "So I'll move the {service} visit to {when}.", label="Read-back (move)", variables=("service", "when")),
        line("confirm_move", "Is that right?", label="Confirm question (move)", static=True),
        line("readback_cancel", "Shall I cancel the {service} visit {when}?", label="Read-back (cancel)", variables=("service", "when")),
        line("price", "The call-out charge is {visit}; the technician will quote the rest after inspection.", label="Price (visit charge)", variables=("visit",)),
        line("price_range", "The call-out charge is {visit}; the job usually costs {low} to {high}, final after inspection.", label="Price (with usual range)", variables=("visit", "low", "high")),
        line("closing_booked", "Your booking is confirmed — {when}. The technician will call before coming.", label="After booking", variables=("when",)),
        line("closing_rescheduled", "The visit is now {when}.", label="After moving", variables=("when",)),
        line("closing_confirmed", "The technician will come as scheduled.", label="Visit confirmed", static=True),
        line("closing_cancelled", "Alright, the booking has been cancelled. Call us any time.", label="After cancelling", static=True),
        line("closing_lead", "One of our team will get in touch with you.", label="Request kept for a call back", static=True),
        line("knows_person", "We have a service booking under the name {name}. Do you know them?", label="Someone else answered", variables=("name",)),
    )

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text(key, language) for key in ("closing_confirmed", "closing_cancelled", "closing_lead")]


__all__ = [
    "AddressSkill",
    "AnotherDaySkill",
    "BookFirstIntentSkill",
    "HomeConfirmSkill",
    "ProblemSkill",
    "ServiceSkill",
    "TimeOkSkill",
]
