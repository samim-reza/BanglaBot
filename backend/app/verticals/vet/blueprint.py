"""The vet clinic's call pipelines — the clinic's, with vets, the owner and the pet, and animal emergencies::

    greet → intent ─ book ───────▶ vet → day → new client* → owner's name → pet's name → species → phone
                   │                → visit mode* → payment* → approval* → read-back → book → text
                   ├ reschedule ─▶ find appointment → day → read-back → move
                   └ cancel ─────▶ find appointment → read-back → cancel
    (* off by default.)  Outbound reminder: as the clinic's, naming the pet.
"""

from __future__ import annotations

from typing import Any

from app.skills.library.customer_type import CustomerTypeSkill
from app.skills.library.intake import IntakeField, IntakeSkill
from app.skills.library.lines import L, line
from app.skills.library.phone import PhoneSkill
from app.verticals.clinic.blueprint import inbound_blueprint, inbound_skills, outbound_blueprint, schedule_skill
from app.verticals.clinic.skills import DoctorSkill
from app.verticals.vet.flow import VetFlow
from app.verticals.vet.skills import VetAttendSkill, VetEmergencySkill, vet_confirm

RED_FLAGS = (
    "poisoning (chocolate, xylitol, antifreeze, rat poison, human medicines)", "can't breathe or struggling to breathe",
    "hit by a car or a bad fall", "seizure", "heavy bleeding", "bloated, hard belly or retching without vomiting", "collapse",
)

SPECIES = ("dog", "cat", "bird", "rabbit", "other")

VET_FIELDS = (
    IntakeField("owner_name", L("Owner's name"), L("May I have your name?"), required=True, long_answer=True, hint="The caller — the pet's owner."),
    IntakeField("pet_name", L("Pet's name"), L("And what's your pet's name?"), required=True),
    IntakeField("species", L("Species"), L("Is it a dog, a cat, a bird, a rabbit, or something else?"), type="choice", choices=SPECIES),
    IntakeField("breed", L("Breed"), L("What breed is your pet?"), on=False),
    IntakeField("pet_age", L("Pet's age"), L("How old is your pet?"), on=False),
    IntakeField("email", L("Email"), L("What email should we send the details to?"), type="email", on=False),
    IntakeField("reason", L("Reason for visit"), L("What is the visit for, briefly?"), ask=False, hint="A few words (vaccination, check-up, not eating …), only if the caller says it. Never ask for symptoms in detail."),
)

VET_LINES = (
    line("doctor", "Which vet would you like to see? We have {departments}.", label="Ask for a vet", variables=("departments",)),
    line("choose", "We have {names} — who would you like to see?", label="Several match", variables=("names",)),
    line("unknown", "Sorry, I can't find that vet. We have {departments}. Who would you like to see?", label="No match", variables=("departments",)),
)

SCHEDULE_LINES = (
    line("ask", "{who} sees pets {schedule}. Which day would you like to come?", label="Ask for a day", variables=("who", "schedule")),
    line("ask_short", "Which day would you like?", label="Ask again", static=True),
)


def vet_skills() -> dict[str, Any]:
    skills = inbound_skills(VET_FIELDS)
    schedule = schedule_skill(lambda slots, ctx: slots.get("intent") in ("book", "reschedule"))
    schedule.lines = SCHEDULE_LINES
    for skill in (
        DoctorSkill(lines=VET_LINES, label=L("Vet"), description=L("Finds the right vet by name, specialty or the pet's need."), goal="Find out which vet (save the D-ref)."),
        schedule,
        CustomerTypeSkill(
            "patient_type",
            slot="patient_type",
            noun="client",
            label=L("New or returning client"),
            lines=(line("ask", "Has your pet been to us before?", label="Ask new or returning", static=True),),
            goal="Find out whether the pet has been here before.",
        ),
        IntakeSkill(VET_FIELDS, label=L("Owner and pet"), goal="Get the owner's and the pet's details."),
        PhoneSkill(goal="Get the owner's mobile number."),
        VetEmergencySkill(red_flags=RED_FLAGS),
        vet_confirm(),
    ):
        skills[skill.key] = skill
    return skills


INBOUND = inbound_blueprint("vet", vet_skills(), flow_cls=VetFlow)
OUTBOUND = outbound_blueprint(
    "vet",
    red_flags=RED_FLAGS,
    flow_cls=VetFlow,
    overrides={"confirm": vet_confirm(), "attend": VetAttendSkill(), "emergency": VetEmergencySkill(red_flags=RED_FLAGS)},
)
BLUEPRINTS = {"inbound": INBOUND, "outbound": OUTBOUND}

__all__ = ["BLUEPRINTS", "INBOUND", "OUTBOUND", "RED_FLAGS", "SPECIES", "VET_FIELDS", "vet_skills"]
