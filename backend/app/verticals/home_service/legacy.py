"""Home-service engine: plumber, electrician, AC servicing, cleaning, pest control…

Inbound — a customer calls with a job:

    service → problem → name → address (+ service-area check) → day
            → arrival window (backend picks the requested / earliest free one)
            → [phone] → read-back with the visit charge → booked

Outbound — the company confirms a booked visit (day before):

    identity → is the time OK? ─ yes → confirmed
                               └ no → another day? ─ yes → day → read-back → moved
                                                  └ no → cancelled

A booking is an *arrival window* ("tomorrow, 9 am to 12 noon"), never an
exact minute; capacity per window = how many teams the company sends out.
The agent quotes only the visit charge and the catalog's price range — the
final price is the technician's after inspection. Gas smell / sparks / fire
are emergencies: the caller is told to get to safety and call 999.
"""

from __future__ import annotations

from typing import Any

from app.flows.base import (
    OUTCOME_BOOKED,
    OUTCOME_CANCELLED,
    OUTCOME_CONFIRMED,
    OUTCOME_EMERGENCY,
    OUTCOME_LEAD,
    OUTCOME_RESCHEDULED,
    STAGE_COMMIT,
    CommitAction,
    CommitResult,
    Instruction,
    Terminal,
)
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.flows.steps import CONFIRMED, STAGE_CONFIRM, SlotSpec, StepFlow, lang_text
from app.flows.timefmt import calendar_facts, normalize_days
from app.verticals.base import FieldSpec, L, Vertical
from app.verticals.common import (
    clear_notice,
    join_and,
    money,
    notice,
    plan_booking,
    slot_start,
    when_phrase,
    window_phrase,
    with_notice,
)
from app.verticals.reception import PHONE_HINT, caller_phone, clean_phone
from app.voice.languages import normalize_language, phrase

KIND_SERVICE = "service"
KIND_BOOKING = "booking"

SERVICE = "service"
PROBLEM = "problem"
NAME = "customer_name"
ADDRESS = "address"
DATE = "date"
PHONE = "phone"
TIME_OK = "time_ok"
NEW_TIME = "wants_new_time"

DEFAULT_WINDOWS = [
    {"key": "morning", "start": "09:00", "end": "12:00"},
    {"key": "afternoon", "start": "12:00", "end": "15:00"},
    {"key": "evening", "start": "15:00", "end": "18:00"},
]

_LINES: dict[str, dict[str, str]] = {
    "opening_question": {
        "bn": "কী ধরনের সার্ভিস প্রয়োজন, বলুন?",
        "en": "What service do you need today?",
    },
    "service": {
        "bn": "কোন সার্ভিসটা লাগবে? আমরা {services} করি।",
        "en": "Which service do you need? We do {services}.",
    },
    "service_choose": {
        "bn": "এর মধ্যে কোনটা — {names}?",
        "en": "Which one — {names}?",
    },
    "problem": {
        "bn": "সমস্যাটা একটু বলবেন?",
        "en": "Could you briefly describe the problem?",
    },
    "customer_name": {"bn": "আপনার নামটা বলবেন?", "en": "May I have your name?"},
    "address": {
        "bn": "কাজটা কোন ঠিকানায় হবে? এলাকা, রোড আর বাসা নম্বর বলুন।",
        "en": "What's the address for the job — area, road and house number?",
    },
    "out_of_area": {
        "bn": "দুঃখিত, ওই এলাকায় আমাদের সার্ভিস এখনো নেই — আমরা {areas} এলাকায় কাজ করি। এর মধ্যে কোনো ঠিকানায় লাগলে বলুন।",
        "en": "Sorry, we don't cover that area yet — we work in {areas}. Tell me if the job is at an address there.",
    },
    "date": {
        "bn": "কোন দিন আসলে সুবিধা হয়?",
        "en": "Which day suits you?",
    },
    "phone": {"bn": "আপনার মোবাইল নম্বরটা বলবেন?", "en": "What's your mobile number?"},
    "readback": {
        "bn": "তাহলে {service} এর জন্য {when} আমাদের টেকনিশিয়ান {address} এ যাবেন। {price} বুকিংটা কনফার্ম করব?",
        "en": "So a technician will come to {address} {when} for {service}. {price} Shall I confirm the booking?",
    },
    "readback_move": {
        "bn": "তাহলে {service} এর ভিজিটটা সরিয়ে {when} করে দিচ্ছি। ঠিক আছে?",
        "en": "So I'll move the {service} visit to {when}. Is that right?",
    },
    "price": {
        "bn": "ভিজিটিং চার্জ {visit}, কাজ দেখে টেকনিশিয়ান বাকি খরচ জানাবেন।",
        "en": "The call-out charge is {visit}; the technician will quote the rest after inspection.",
    },
    "price_range": {
        "bn": "ভিজিটিং চার্জ {visit}; কাজের খরচ সাধারণত {low} থেকে {high}, কাজ দেখে চূড়ান্ত হবে।",
        "en": "The call-out charge is {visit}; the job usually costs {low} to {high}, final after inspection.",
    },
    "time_ok": {
        "bn": "{when} আপনার {service} এর জন্য আমাদের টেকনিশিয়ান যাবেন। সময়টা কি ঠিক আছে?",
        "en": "Our technician is coming {when} for your {service}. Does that time still work?",
    },
    "new_time": {
        "bn": "ঠিক আছে। অন্য কোনো দিনে পাঠালে হবে?",
        "en": "Alright. Shall we come on another day instead?",
    },
    "closing_booked": {
        "bn": "আপনার বুকিং কনফার্ম হয়েছে — {when}। টেকনিশিয়ান যাওয়ার আগে ফোন করবেন। ধন্যবাদ, ভালো থাকবেন।",
        "en": "Your booking is confirmed — {when}. The technician will call before coming. Thank you, goodbye.",
    },
    "closing_rescheduled": {
        "bn": "ভিজিটটা {when} করা হয়েছে। ধন্যবাদ, ভালো থাকবেন।",
        "en": "The visit is now {when}. Thank you, goodbye.",
    },
    "closing_confirmed": {
        "bn": "ধন্যবাদ, তাহলে নির্ধারিত সময়েই টেকনিশিয়ান যাবেন। ভালো থাকবেন।",
        "en": "Thank you, the technician will come as scheduled. Goodbye.",
    },
    "closing_cancelled": {
        "bn": "ঠিক আছে, বুকিংটা বাতিল করা হলো। দরকার হলে আবার ফোন করবেন। ভালো থাকবেন।",
        "en": "Alright, the booking has been cancelled. Call us any time. Goodbye.",
    },
    "closing_lead": {
        "bn": "ধন্যবাদ। আমাদের একজন প্রতিনিধি আপনার সাথে যোগাযোগ করবেন। ভালো থাকবেন।",
        "en": "Thank you. One of our team will get in touch with you. Goodbye.",
    },
    "emergency": {
        "bn": "এটা বিপজ্জনক হতে পারে। এখনই সবাই নিরাপদ জায়গায় সরে যান, কোনো সুইচ বা আগুন জ্বালাবেন না, আর সাথে সাথে {emergency} নম্বরে ফোন করুন।",
        "en": "This could be dangerous. Get everyone to a safe place now, don't touch any switch or flame, and call {emergency} right away.",
    },
    "knows_person": {
        "bn": "{name} এর নামে আমাদের একটি সার্ভিস বুকিং আছে। আপনি কি ওনাকে চেনেন?",
        "en": "We have a service booking under the name {name}. Do you know them?",
    },
}

_RULES = """You are the phone assistant of a home-services company (e.g. AC / heating, plumbing, electrical, cleaning, pest control, appliance repair). You book technician visits.
- Map the caller's problem to one service from the list and save its ref (S1, S2, …) as `service`; save their description (a few words) as `problem`. If two services could fit, let the system ask.
- Price: only the visit charge and the usual price range from the list. Never promise an exact job price or an exact arrival minute — the technician quotes after inspection and comes within the booked window.
- Never give do-it-yourself repair instructions for gas or electrical work.
- Emergency (gas smell or leak, sparks, burning smell from wiring, fire, electric shock, major flooding near electrics): call report_emergency immediately.
- Address: save the full address as `address` and the neighbourhood / locality as `area`.
- Dates: save `date` as YYYY-MM-DD from the calendar below; a preferred arrival window goes in `time_window` (morning / afternoon / evening). The system picks the window, reads the booking back and writes it. Never say a booking is confirmed before a tool result says so."""


def service_config(ctx: CallContext) -> dict[str, Any]:
    return HOME_SERVICE.config(ctx.merchant)


def service_availability(ctx: CallContext) -> Availability:
    config = service_config(ctx)
    days = normalize_days(config.get("working_days") or [])
    windows = []
    for raw in config.get("time_windows") or DEFAULT_WINDOWS:
        if not isinstance(raw, dict):
            continue
        window = window_from_config(
            {**raw, "days": days, "slot_minutes": 0, "capacity": config.get("teams") or 1},
        )
        if window is not None:
            windows.append(window)
    return Availability(
        windows=windows,
        item_id=None,
        horizon_days=int(config.get("booking_horizon_days") or 7),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 60),
        busy=ctx.busy_for(None),
    )


def window_label(key: str, ctx: CallContext, language: str) -> str:
    for raw in service_config(ctx).get("time_windows") or DEFAULT_WINDOWS:
        if isinstance(raw, dict) and raw.get("key") == key:
            span = window_phrase(raw.get("start"), raw.get("end"), language)
            return f"{span}র মধ্যে" if normalize_language(language) == "bn" else f"between {span.replace(' to ', ' and ')}"
    return ""


def _area_ok(area: Any, ctx: CallContext) -> bool:
    areas = [str(item).strip().lower() for item in service_config(ctx).get("service_areas") or [] if str(item).strip()]
    if not areas:
        return True
    text = " ".join(str(area or "").lower().split())
    return bool(text) and any(name in text or text in name for name in areas)


class HomeServiceFlow(StepFlow):
    vertical = "home_service"
    long_answer_stages = frozenset({PROBLEM, ADDRESS, PHONE})

    def __init__(self, direction: str) -> None:
        self.direction = direction
        self.key = f"home_service.{direction}"
        self.identity_gate = direction != DIRECTION_INBOUND

    slot_specs = (
        SlotSpec("service", "The service, as the ref from the service list (S1, S2, …) — or its name if unsure.", directions=('inbound',)),
        SlotSpec("problem", "The problem in the caller's words, short (e.g. 'AC leaking water', 'kitchen sink blocked').", directions=('inbound',)),
        SlotSpec("customer_name", "The caller's name."),
        SlotSpec("address", "Full job address as said (area, road, house, floor, landmark)."),
        SlotSpec("area", "Locality / thana of the address (e.g. Dhanmondi, Mirpur 10). If it is one of the service areas in the facts, spell it exactly as listed."),
        SlotSpec("date", "Visit date as YYYY-MM-DD. Convert a day the caller names ('tomorrow', 'Friday') with the calendar in the facts."),
        SlotSpec("time_window", "Preferred arrival window.", {"type": "string", "enum": ["morning", "afternoon", "evening"]}),
        SlotSpec("phone", f"Mobile number, digits only. {PHONE_HINT}"),
        SlotSpec("time_ok", "Confirmation call: true = the booked time works, false = it doesn't.", {"type": "boolean"}, gated=True, directions=('outbound',)),
        SlotSpec("wants_new_time", "After the time doesn't work: true = another day, false = cancel the booking.", {"type": "boolean"}, directions=('outbound',)),
    )
    yes_no_stages = {STAGE_CONFIRM: CONFIRMED, TIME_OK: "time_ok", NEW_TIME: "wants_new_time"}
    stage_goals = {
        SERVICE: "Which service do they need (map their problem to a service ref)?",
        PROBLEM: "A short description of the problem.",
        NAME: "The caller's name.",
        ADDRESS: "The job address (save address and area).",
        DATE: "Which day (and a preferred arrival window if they say one).",
        PHONE: "A mobile number.",
        TIME_OK: "Does the booked visit time still work?",
        NEW_TIME: "Another day, or cancel?",
    }
    stage_slots = {
        SERVICE: ("service", "problem"),
        PROBLEM: ("problem",),
        NAME: ("customer_name",),
        ADDRESS: ("address", "area"),
        DATE: ("date", "time_window"),
        PHONE: ("phone",),
        TIME_OK: ("time_ok",),
        NEW_TIME: ("wants_new_time",),
    }

    @property
    def gated_slots(self) -> tuple[str, ...]:  # type: ignore[override]
        return ("time_ok", CONFIRMED)

    # ---- context -------------------------------------------------------------------
    def _service(self, slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
        found = ctx.find_items(slots.get("service"), KIND_SERVICE) if slots.get("service") else []
        return found[0] if len(found) == 1 else None

    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        if ctx.direction == DIRECTION_INBOUND:
            services = ctx.items(KIND_SERVICE)
            return {"service": services[0].ref} if len(services) == 1 else {}
        slots: dict[str, Any] = {"customer_name": ctx.record_value("customer_name", "")}
        item = ctx.item_by_id(getattr(ctx.record, "catalog_item_id", None))
        if item is not None:
            slots["service"] = item.ref
        if ctx.record_value("address", ""):
            slots["address"] = ctx.record_value("address", "")
        return slots

    def normalize(self, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        fields = dict(fields)
        lang = normalize_language(language)
        if "service" in fields:
            found = ctx.find_items(fields["service"], KIND_SERVICE, fields=("category",))
            if len(found) == 1:
                fields["service"] = found[0].ref
            else:
                fields.pop("service")
                if found:
                    line = lang_text(_LINES["service_choose"], lang).format(names=join_and([item.name for item in found[:4]], lang))
                else:
                    line = lang_text(_LINES["service"], lang).format(services=self._services_phrase(ctx, lang))
                return fields, Instruction(SERVICE, line, verbatim=True)
        # Only the locality is checked: a free-form address in another script would
        # never match the list reliably, and a wrong "we don't cover you" loses a job.
        if fields.get("area") and not _area_ok(fields.get("area"), ctx):
            fields.pop("area", None)
            fields.pop("address", None)
            areas = join_and([str(a) for a in service_config(ctx).get("service_areas") or []][:6], lang)
            return fields, Instruction(ADDRESS, lang_text(_LINES["out_of_area"], lang).format(areas=areas), verbatim=True)
        if "phone" in fields:
            phone = clean_phone(fields["phone"])
            if not phone:
                fields.pop("phone")
                return fields, Instruction(PHONE, phrase("phone_invalid", lang), verbatim=True)
            fields["phone"] = phone
        return fields, None

    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        clear_notice(slots)
        super().on_saved(saved, slots, ctx)
        if saved.get("time_ok") is True:
            slots[CONFIRMED] = True

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        needs_slot = ctx.direction == DIRECTION_INBOUND or slots.get("wants_new_time") is True
        if not needs_slot:
            for key in ("slot", "serial", "window"):
                slots.pop(key, None)
            return
        plan_booking(slots, ctx, service_availability(ctx), pref_key="", window_key="time_window")

    # ---- cascade -------------------------------------------------------------------
    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        gate = self.identity_stage(slots)
        if gate is not None:
            return gate
        if slots.get("decision"):
            return self.tail(slots)
        if ctx.direction != DIRECTION_INBOUND:
            ok = slots.get("time_ok")
            if ok is None:
                return TIME_OK
            if ok is True:
                return self.tail(slots)
            wants = slots.get("wants_new_time")
            if wants is None:
                return NEW_TIME
            if wants is False:
                return STAGE_COMMIT
            if not slots.get("date") or not slots.get("slot"):
                return DATE
            return self.tail(slots)
        if not slots.get("service"):
            return SERVICE
        if not slots.get("problem"):
            return PROBLEM
        if not slots.get("customer_name"):
            return NAME
        if not slots.get("address"):
            return ADDRESS
        if not slots.get("date") or not slots.get("slot"):
            return DATE
        if not caller_phone(slots, ctx):
            return PHONE
        return self.tail(slots)

    # ---- lines ---------------------------------------------------------------------
    def _services_phrase(self, ctx: CallContext, lang: str) -> str:
        return join_and([item.name for item in ctx.items(KIND_SERVICE)][:6], lang)

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

    def _when(self, slots: dict[str, Any], ctx: CallContext, lang: str, *, on: bool = False) -> str:
        start = slot_start(slots)
        if start is None:
            return ""
        return when_phrase(start, ctx, lang, window_label=window_label(str(slots.get("window") or ""), ctx, lang), on=on)

    def _record_when(self, ctx: CallContext, lang: str) -> str:
        start = getattr(ctx.record, "scheduled_at", None)
        if start is None:
            return ""
        local = start.astimezone(ctx.now.tzinfo)
        details = ctx.record_details()
        return when_phrase(local, ctx, lang, window_label=window_label(str(details.get("time_window") or ""), ctx, lang), on=True)

    def _price_sentence(self, service: CatalogEntry | None, ctx: CallContext, lang: str) -> str:
        if service is None or not service.get("visit_charge"):
            return ""
        visit = money(service.get("visit_charge"), ctx, lang)
        low, high = service.get("price_from"), service.get("price_to")
        if low and high:
            return lang_text(_LINES["price_range"], lang).format(visit=visit, low=money(low, ctx, lang), high=money(high, ctx, lang))
        return lang_text(_LINES["price"], lang).format(visit=visit)

    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        service = self._service(slots, ctx)
        texts = {
            SERVICE: t("service").format(services=self._services_phrase(ctx, lang)),
            PROBLEM: t("problem"),
            NAME: t("customer_name"),
            ADDRESS: t("address"),
            DATE: t("date"),
            PHONE: t("phone"),
            NEW_TIME: t("new_time"),
        }
        if stage in texts:
            return with_notice(slots, ctx, lang, texts[stage])
        if stage == TIME_OK:
            return t("time_ok").format(when=self._record_when(ctx, lang), service=service.name if service else "")
        if stage == STAGE_CONFIRM:
            if ctx.direction != DIRECTION_INBOUND:
                line = t("readback_move").format(service=service.name if service else "", when=self._when(slots, ctx, lang))
            else:
                line = t("readback").format(
                    service=service.name if service else "",
                    when=self._when(slots, ctx, lang, on=True),
                    address=slots.get("address", ""),
                    price=self._price_sentence(service, ctx, lang),
                )
                line = " ".join(line.split())
            return with_notice(slots, ctx, lang, line)
        return ""

    # ---- commit --------------------------------------------------------------------
    def commit_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        service = self._service(slots, ctx)
        record_id = (str(getattr(ctx.record, "id", "") or "") or None) if ctx.direction != DIRECTION_INBOUND else None
        teams = int(service_config(ctx).get("teams") or 1)
        if ctx.direction != DIRECTION_INBOUND:
            if slots.get("time_ok") is True:
                return CommitAction(outcome=OUTCOME_CONFIRMED, status="confirmed", record_id=record_id)
            if slots.get("wants_new_time") is False:
                return CommitAction(outcome=OUTCOME_CANCELLED, status="cancelled", record_id=record_id)
            start = slot_start(slots)
            if start is None:
                return None
            return CommitAction(
                outcome=OUTCOME_RESCHEDULED,
                status="confirmed",
                record_id=record_id,
                fields={"scheduled_at": start, "details": {"time_window": slots.get("window", "")}},
                capacity=(None, start, teams),
            )
        start = slot_start(slots)
        if service is None or start is None:
            return None
        return CommitAction(
            outcome=OUTCOME_BOOKED,
            status="confirmed",
            fields={
                "kind": KIND_BOOKING,
                "customer_name": slots.get("customer_name", ""),
                "customer_phone": caller_phone(slots, ctx),
                "address": slots.get("address", ""),
                "catalog_item_id": service.id,
                "scheduled_at": start,
                "items_summary": service.name,
                "total_amount": service.get("visit_charge") or 0,
                "details": {
                    "problem": slots.get("problem", ""),
                    "area": slots.get("area", ""),
                    "time_window": slots.get("window", ""),
                    "service": service.name,
                },
            },
            capacity=(None, start, teams),
        )

    def fallback_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        """Inbound caller who stopped before booking (e.g. outside the service area): keep the request."""
        if ctx.direction != DIRECTION_INBOUND or not (slots.get("service") or slots.get("problem")):
            return None
        phone = caller_phone(slots, ctx)
        if not phone:
            return None
        service = self._service(slots, ctx)
        return CommitAction(
            outcome=OUTCOME_LEAD,
            status="needs_review",
            fields={
                "kind": KIND_BOOKING,
                "customer_name": slots.get("customer_name", ""),
                "customer_phone": phone,
                "address": slots.get("address", ""),
                "catalog_item_id": service.id if service else None,
                "items_summary": service.name if service else str(slots.get("problem") or ""),
                "details": {"problem": slots.get("problem", ""), "area": slots.get("area", ""), "unfinished": True},
            },
        )

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        if result.reason != "slot_taken":
            return None
        start = slot_start(slots)
        if start is not None:
            ctx.mark_booked(None, start, 99)
        slots[CONFIRMED] = None
        slots.pop("time_window", None)
        self.derive(slots, ctx)
        notice(slots, "slot_taken")
        return None

    def terminals(self) -> list[Terminal]:
        return [
            Terminal(
                name="report_emergency",
                outcome=OUTCOME_EMERGENCY,
                description=(
                    "Danger right now: gas smell or leak, sparks or burning smell from wiring, fire, electric shock, "
                    "water flooding near electrics. Call at once."
                ),
                properties={"what": {"type": "string", "description": "What the caller described, a few words."}},
                note_template={"bn": "জরুরি অবস্থা: {what}", "en": "Emergency: {what}"},
                requires_identity=False,
            )
        ]

    def closing_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        when = self._when(slots, ctx, lang)
        return {
            OUTCOME_BOOKED: t("closing_booked").format(when=when),
            OUTCOME_RESCHEDULED: t("closing_rescheduled").format(when=when),
            OUTCOME_CONFIRMED: t("closing_confirmed"),
            OUTCOME_CANCELLED: t("closing_cancelled"),
            OUTCOME_LEAD: t("closing_lead"),
            OUTCOME_EMERGENCY: t("emergency").format(emergency=ctx.say_number(ctx.emergency_number, lang)),
        }.get(outcome) or super().closing_line(outcome, slots, ctx, lang)

    # ---- prompt parts ----------------------------------------------------------------
    def rules(self, language: str) -> str:
        return _RULES

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        config = service_config(ctx)
        lines = [f"Services (ref: name — category, visit charge, usual price range in {ctx.currency}, notes):"]
        for item in ctx.items(KIND_SERVICE):
            parts = [f"{item.ref}: {item.name}"]
            if item.get("category"):
                parts.append(f"— {item.get('category')}")
            if item.get("visit_charge"):
                parts.append(f"; visit charge {item.get('visit_charge')}")
            if item.get("price_from") and item.get("price_to"):
                parts.append(f"; usually {item.get('price_from')}–{item.get('price_to')}")
            if item.get("duration"):
                parts.append(f"; takes {item.get('duration')}")
            if item.get("notes"):
                parts.append(f"; {item.get('notes')}")
            lines.append("- " + " ".join(parts))
        if len(lines) == 1:
            lines.append("- (no services added yet — take the request; the team will call back)")
        areas = [str(a) for a in config.get("service_areas") or [] if str(a).strip()]
        lines.append(f"Service areas: {', '.join(areas)}." if areas else "Service areas: anywhere in the city.")
        windows = ", ".join(
            f"{raw.get('key')} {raw.get('start')}–{raw.get('end')}" for raw in config.get("time_windows") or DEFAULT_WINDOWS if isinstance(raw, dict)
        )
        days = ", ".join(normalize_days(config.get("working_days") or [])) or "every day"
        lines.append(f"Arrival windows: {windows}; working days: {days}.")
        lines.append(f"Emergency number: {ctx.emergency_number}.")
        return lines

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lines = [calendar_facts(ctx.today, ctx.now.time().replace(second=0, microsecond=0))]
        if ctx.direction == DIRECTION_INBOUND:
            lines.append(
                f"Caller's number: {ctx.caller_number}." if ctx.caller_number else "Caller's number is unknown — the system will ask for it."
            )
        else:
            item = ctx.item_by_id(getattr(ctx.record, "catalog_item_id", None))
            start = getattr(ctx.record, "scheduled_at", None)
            stamp = start.astimezone(ctx.now.tzinfo).strftime("%a %Y-%m-%d %H:%M") if start else "?"
            lines.append(
                f"This call confirms {self.person_name(ctx)}'s booking: {item.name if item else 'service'} on {stamp} "
                f"at {ctx.record_value('address', '?')}."
            )
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        hints = [str(ctx.merchant_value("business_name", ""))]
        hints += [item.name for item in ctx.items(KIND_SERVICE)][:8]
        hints += [str(a) for a in service_config(ctx).get("service_areas") or []][:10]
        return hints

    # ---- prefetch / preview --------------------------------------------------------------
    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        t = lambda key: lang_text(_LINES[key], lang)  # noqa: E731
        lines = super().prefetch_lines(ctx, lang) + [
            t("problem"), t("customer_name"), t("address"), t("date"), t("phone"), t("new_time"),
            t("closing_confirmed"), t("closing_cancelled"), t("closing_lead"),
            t("emergency").format(emergency=ctx.say_number(ctx.emergency_number, lang)),
            t("service").format(services=self._services_phrase(ctx, lang)),
            phrase("amend_question", lang), phrase("phone_invalid", lang), phrase("closing_inquiry", lang),
        ]
        return lines

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        if ctx.direction == DIRECTION_INBOUND:
            if lang == "bn":
                return [
                    f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                    "সার্ভিস ও সমস্যা: আপনার সার্ভিস তালিকা থেকে মিলিয়ে নেয়।",
                    "নাম ও ঠিকানা: সার্ভিস এলাকার বাইরে হলে জানিয়ে দেয়।",
                    "দিন ও সময়: খালি টাইম-উইন্ডো (সকাল/দুপুর/বিকেল) বেছে নেয়।",
                    "পড়ে শোনানো: সার্ভিস, সময়, ঠিকানা ও ভিজিটিং চার্জ — 'হ্যাঁ' বললে বুক হয়।",
                    f"জরুরি (গ্যাস লিক, স্পার্ক, আগুন): নিরাপদে সরে {ctx.emergency_number}-এ ফোন করতে বলে।",
                ]
            return [
                f"Greeting: \"{self.opening(ctx, lang)}\"",
                "Service and problem: matched against your service list.",
                "Name and address: tells the caller when the address is outside your service areas.",
                "Day and time: picks a free arrival window (morning / afternoon / evening).",
                "Read-back: service, window, address and visit charge — booked on a 'yes'.",
                f"Emergencies (gas leak, sparks, fire): tells the caller to get safe and call {ctx.emergency_number}.",
            ]
        if lang == "bn":
            return [
                f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                "কনফার্মেশন: বুকিংয়ের দিন ও সময় বলে জিজ্ঞেস করে ঠিক আছে কি না।",
                "না হলে: অন্য দিনে সরায়, না চাইলে বাতিল করে।",
            ]
        return [
            f"Greeting: \"{self.opening(ctx, lang)}\"",
            "Confirmation: states the booked day and window and asks whether it still works.",
            "If not: moves it to another day, otherwise cancels.",
        ]


INBOUND = HomeServiceFlow(DIRECTION_INBOUND)
OUTBOUND = HomeServiceFlow("outbound")


def _summary(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    service = names.get(str(getattr(record, "catalog_item_id", "") or ""), "") or str(getattr(record, "items_summary", "") or "")
    problem = details.get("problem", "") if isinstance(details, dict) else ""
    window = details.get("time_window", "") if isinstance(details, dict) else ""
    return " · ".join(part for part in (service, str(problem or ""), str(window or "")) if part)


HOME_SERVICE = Vertical(
    key="home_service",
    label=L("Home services", "হোম সার্ভিস"),
    description=L(
        "Answers the service line: takes the job (service, problem, address), checks the service area, books an arrival window with the visit charge, and confirms visits by phone.",
        "সার্ভিস লাইনের ফোন ধরে: সার্ভিস, সমস্যা ও ঠিকানা নেয়, এলাকা যাচাই করে, ভিজিটিং চার্জসহ টাইম-উইন্ডো বুক করে, আর ভিজিটের আগে কনফার্মেশন কল করে।",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking", "বুকিং"),
    record_label_plural=L("Bookings", "বুকিং"),
    record_fields=(
        FieldSpec("customer_name", L("Customer name", "কাস্টমারের নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Service", "সার্ভিস"), "catalog", required=True, list_column=True),
        FieldSpec("problem", L("Problem", "সমস্যা"), "textarea"),
        FieldSpec("address", L("Address", "ঠিকানা"), "textarea", required=True),
        FieldSpec("scheduled_at", L("Visit (window start)", "ভিজিট (শুরুর সময়)"), "datetime", required=True, list_column=True),
        FieldSpec(
            "time_window",
            L("Arrival window", "টাইম-উইন্ডো"),
            "select",
            options=(("morning", L("Morning", "সকাল")), ("afternoon", L("Afternoon", "দুপুর")), ("evening", L("Evening", "বিকেল"))),
        ),
        FieldSpec("total_amount", L("Visit charge", "ভিজিটিং চার্জ"), "money"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_SERVICE,
    catalog_label=L("Service", "সার্ভিস"),
    catalog_label_plural=L("Services", "সার্ভিস"),
    catalog_fields=(
        FieldSpec("name", L("Service name", "সার্ভিসের নাম"), required=True, placeholder="AC servicing"),
        FieldSpec("category", L("Category", "ক্যাটাগরি"), placeholder="AC / Plumbing / Electrical"),
        FieldSpec("visit_charge", L("Visit / call-out charge", "ভিজিটিং চার্জ"), "money", required=True),
        FieldSpec("price_from", L("Usual price from", "সাধারণ খরচ শুরু"), "money"),
        FieldSpec("price_to", L("Usual price up to", "সাধারণ খরচ সর্বোচ্চ"), "money"),
        FieldSpec("duration", L("Typical duration", "সাধারণ সময়"), placeholder="1–2 hours"),
        FieldSpec("notes", L("Notes for the agent", "এজেন্টের জন্য নোট"), "textarea", placeholder="Gas refill priced separately."),
    ),
    config_fields=(
        FieldSpec("service_areas", L("Service areas", "সার্ভিস এলাকা"), "list", help=L("One area per line; empty = anywhere", "প্রতি লাইনে একটি এলাকা; খালি = সব জায়গা")),
        FieldSpec("working_days", L("Working days", "কাজের দিন"), "days", default=["mon", "tue", "wed", "thu", "fri", "sat"]),
        FieldSpec("teams", L("Teams per time window", "প্রতি উইন্ডোতে টিম"), "number", default=3),
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=7),
    ),
    config_defaults={
        "service_areas": [],
        "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        "time_windows": DEFAULT_WINDOWS,
        "teams": 3,
        "booking_horizon_days": 7,
        "lead_minutes": 60,
    },
    status_labels={
        "pending": L("Requested", "অনুরোধ"),
        "confirmed": L("Booked", "বুকড"),
        "cancelled": L("Cancelled", "বাতিল"),
        "needs_review": L("Call back", "কলব্যাক"),
    },
    flows={"inbound": INBOUND, "outbound": OUTBOUND},
    outbound_label=L("Confirmation call", "কনফার্মেশন কল"),
    scheduled=True,
    summarize=_summary,
)

__all__ = ["HOME_SERVICE", "HomeServiceFlow", "service_availability"]
