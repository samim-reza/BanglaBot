"""The real-estate call pipelines: which skills, in what order, per branch.

Inbound::

    greet → intent ─ buy / rent ─▶ name → property type → area → budget → timeline
                   │                → listings that fit (model) → site visit? ─ yes → day → phone* → read-back → visit booked
                   │                                                         └ no → phone* → lead for an agent
                   └ sell ───────▶ name → property type → area → size → asking price → phone* → read-back → seller lead
    (* skipped when caller ID gives the number)

Outbound follow-up: identity → still interested? ─ no → not interested
                                                 └ yes → (missing details) → listings → visit …

Leads are scored in code (hot / warm / cold), never by the model.
"""

from __future__ import annotations

from typing import Any

from app.flows.steps import SlotSpec
from app.pipeline.blueprint import Blueprint, Branch
from app.skills.library.greet import FarewellSkill, GreetSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.lines import L2, line
from app.skills.library.notify import NotifySkill
from app.skills.library.phone import PhoneSkill
from app.skills.library.schedule import ScheduleSkill
from app.verticals.real_estate.catalog import PROPERTY_TYPES, TIMELINES, visit_availability
from app.verticals.real_estate.flow import RealEstateFlow
from app.verticals.real_estate.skills import InterestedSkill, LeadIntentSkill, NeedSkill, PitchSkill, RealtyConfirmSkill

CALLER_FIELDS = (
    IntakeField("caller_name", L2("Name", "নাম"), L2("May I have your name, please?", "আপনার নামটা একটু বলবেন?"), required=True, hint="The caller's name."),
    IntakeField("email", L2("Email", "ইমেইল"), L2("What email should our agent send listings to?", "কোন ইমেইলে প্রপার্টির তথ্য পাঠাব?"), type="email", on=False),
    IntakeField("financing", L2("Financing", "অর্থায়ন"), L2("Will you be paying cash, or with a mortgage?", "নগদে কিনবেন, নাকি লোনে?"), on=False),
)

BUYER = ("intake", "property_type", "location", "budget", "timeline", "listings", "visit", "phone")
SELLER = ("intake", "property_type", "location", "size", "asking_price", "phone")


def need_skills() -> list[Any]:
    return [
        NeedSkill(
            "property_type",
            slots=(SlotSpec("property_type", "Kind of property.", {"type": "string", "enum": PROPERTY_TYPES}),),
            lines=(line("property_type", "What kind of property — an apartment, a house, land, or commercial space?", "কী ধরনের প্রপার্টি — জমি বা প্লট, ফ্ল্যাট, বাড়ি, নাকি কমার্শিয়াল?", label="Ask the property type", static=True),),
            label=L2("Property type", "প্রপার্টির ধরন"),
            goal="Which kind of property (land, flat, house, commercial)?",
        ),
        NeedSkill(
            "location",
            slots=(SlotSpec("location", "Area they want (buyers/renters) or where their property is (sellers), as said."),),
            lines=(
                line("location", "Which area are you looking in?", "কোন এলাকায় খুঁজছেন?", label="Ask the area", static=True),
                line("location_sell", "Where is the property located?", "প্রপার্টিটা কোন এলাকায়?", label="Ask the area (seller)", static=True),
            ),
            long=True,
            label=L2("Area", "এলাকা"),
            goal="Which area?",
        ),
        NeedSkill(
            "budget",
            slots=(
                SlotSpec("budget", "Budget as the caller said it (e.g. '৫০-৬০ লাখ', '25 thousand a month')."),
                SlotSpec("budget_max", "Upper end of the budget as a plain number in the account's currency, when clear.", {"type": "number"}),
            ),
            lines=(
                line("budget", "Roughly what is your budget?", "আপনার বাজেট মোটামুটি কত?", label="Ask the budget", static=True),
                line("budget_rent", "What monthly rent are you looking at?", "মাসিক ভাড়ার বাজেট কত?", label="Ask the budget (rent)", static=True),
            ),
            long=True,
            label=L2("Budget", "বাজেট"),
            goal="Their budget.",
        ),
        NeedSkill(
            "timeline",
            slots=(SlotSpec("timeline", "When they plan to buy / move.", {"type": "string", "enum": TIMELINES}),),
            lines=(
                line("timeline", "When are you planning to buy — right away, or in the next few months?", "কবের মধ্যে নিতে চান — এখনই, নাকি কয়েক মাসের মধ্যে?", label="Ask the timeline", static=True),
                line("timeline_rent", "When would you like to move in?", "কবে থেকে উঠতে চান?", label="Ask the timeline (rent)", static=True),
            ),
            label=L2("Timeline", "সময়সীমা"),
            goal="When they plan to buy or move.",
        ),
        NeedSkill(
            "size",
            slots=(SlotSpec("size", "Size as said (e.g. '৫ কাঠা', '1200 sq ft', '3 bed')."),),
            lines=(line("size", "How big is it?", "জায়গাটা কত বড় — কত কাঠা বা কত স্কয়ার ফিট?", label="Ask the size", static=True),),
            long=True,
            label=L2("Size", "আকার"),
            goal="Size of the seller's property.",
        ),
        NeedSkill(
            "asking_price",
            slots=(SlotSpec("asking_price", "Sellers: the price they expect, as said."),),
            lines=(line("asking_price", "What price are you expecting?", "কত দাম আশা করছেন?", label="Ask the asking price", static=True),),
            long=True,
            label=L2("Asking price", "প্রত্যাশিত দাম"),
            goal="The seller's expected price.",
        ),
    ]


def visit_skill() -> ScheduleSkill:
    return ScheduleSkill(
        "visit",
        availability=lambda slots, ctx: visit_availability(ctx),
        needed=lambda slots, ctx: slots.get("wants_visit") is True,
        date_key="visit_date",
        pref_key="visit_time_pref",
        slots=(
            SlotSpec("visit_date", "Viewing date as YYYY-MM-DD. Convert a day the caller names ('Saturday', 'tomorrow') with the calendar in the facts."),
            SlotSpec("visit_time_pref", "Preferred visit time: HH:MM (24 h) or morning / afternoon / evening."),
        ),
        lines=(
            line("ask", "Which day would you like to come for a viewing? We do viewings {schedule}.", "কোন দিন সাইট ভিজিটে আসতে চান? আমরা {schedule} সাইট দেখাই।", label="Ask for a day", variables=("schedule",)),
            line("ask_short", "Which day would you like to come for a viewing?", "কোন দিন সাইট ভিজিটে আসতে চান?", label="Ask again", static=True),
        ),
        label=L2("Site visit", "সাইট ভিজিট"),
        goal="Which day for the site visit (and a preferred time if they say one).",
    )


def intent_skill() -> LeadIntentSkill:
    return LeadIntentSkill(
        {"buy": "buy a property", "rent": "rent a property", "sell": "sell their property"},
        lines=(
            line("intent", "Are you looking to buy, to rent, or to sell your property?", "আপনি কি কিনতে চান, ভাড়া নিতে চান, নাকি আপনার জমি বা ফ্ল্যাট বিক্রি করতে চান?", label="Ask what they need", static=True),
            line("branch_off", "Sorry, I can't help with that over the phone, but one of our agents can.", "দুঃখিত, এটা ফোনে করা যাচ্ছে না, আমাদের একজন প্রতিনিধি সাহায্য করবেন।", label="Not offered by phone", static=True),
        ),
        goal="Find out whether they want to buy, rent, or sell.",
    )


def skills(direction: str) -> dict[str, Any]:
    common = [
        FarewellSkill(),
        RealtyConfirmSkill(),
        intent_skill(),
        IntakeSkill(CALLER_FIELDS, label=L2("Caller details", "কলারের তথ্য"), goal="Get the caller's name."),
        *need_skills(),
        PitchSkill(),
        visit_skill(),
        PhoneSkill(goal="A mobile number to reach them."),
        NotifySkill(),
    ]
    if direction == "inbound":
        greet = GreetSkill(lines=(*GreetSkill.lines[:2], line("opening_question", "Are you looking to buy, rent, or sell a property?", "আপনি কি জমি বা ফ্ল্যাট কিনতে, ভাড়া নিতে, নাকি বিক্রি করতে চান?", label="First question", variables=("business",), static=True)))
        common.insert(0, greet)
    else:
        common.append(InterestedSkill())
    return {skill.key: skill for skill in common}


def _branch(key: str, keys: tuple[str, ...], label: dict[str, str]) -> Branch:
    needs = frozenset(k for k in keys if k not in ("intake", "listings", "visit", "phone"))
    before = {"listings": needs, "visit": frozenset({"listings"})} if "listings" in keys else {}
    return Branch(key, keys, label=label, movable=(frozenset({"intake", *needs}),), before=before)


def blueprint(direction: str) -> Blueprint:
    inbound = direction == "inbound"
    return Blueprint(
        key=f"real_estate.{direction}",
        vertical="real_estate",
        direction=direction,
        skills=skills(direction),
        prelude=("intent",) if inbound else ("interested", "intent"),
        router_slot="intent",
        branches={
            "buy": _branch("buy", BUYER, L2("Buyer", "ক্রেতা")),
            "rent": _branch("rent", BUYER, L2("Renter", "ভাড়াটিয়া")),
            "sell": _branch("sell", SELLER, L2("Seller", "বিক্রেতা")),
        },
        default_branch="buy",
        effects=("notify",),
        line_skills=("greet", "farewell", "confirm") if inbound else ("farewell", "confirm"),
        flow_cls=RealEstateFlow,
    )


INBOUND = blueprint("inbound")
OUTBOUND = blueprint("outbound")
BLUEPRINTS = {"inbound": INBOUND, "outbound": OUTBOUND}

__all__ = ["BLUEPRINTS", "BUYER", "CALLER_FIELDS", "INBOUND", "OUTBOUND", "SELLER", "blueprint"]
