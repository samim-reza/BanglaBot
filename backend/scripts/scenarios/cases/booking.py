"""Booking businesses: one profile each (fed to the common scenarios) plus their own special cases."""

from __future__ import annotations

from datetime import datetime

from scripts.scenarios.cases.common import BOOKED, LEAD_ONLY, BookingProfile, common
from scripts.scenarios.dates import say_day
from scripts.scenarios.model import Expect, Persona, Scenario

PROFILES = (
    BookingProfile(
        "clinic", "a check-up with Dr. Sarah Mitchell", "Dr. Sarah Mitchell", "tue", "11:00", "11 am", "thu", "2 pm", "sun",
        "an appointment with a neurologist", "What is Dr. Carter's fee and which days does he work?",
        "Dr. James Carter (Pediatrics) charges $140 and works Monday, Wednesday and Friday, 10 am to 4 pm.",
        emergency="My father has crushing chest pain and his left arm went numb, he's sweating a lot.",
        facts={"reason": "annual check-up", "date of birth": "March 3, 1990", "new or existing patient": "new"},
    ),
    BookingProfile(
        "dental", "a cleaning with Dr. Emily Park", "Dr. Emily Park", "wed", "09:00", "9 am", "thu", "1 pm", "sun",
        "an appointment with Dr. Brown", "Do you see kids, and which dentist does braces and on what days?",
        "Dr. Lisa Gomez is the pediatric dentist (Mon/Wed/Sat); Dr. Raj Patel does braces (Tue/Thu, 10 am-6 pm).",
        emergency="I just knocked out my front tooth playing basketball and it won't stop bleeding.",
        facts={"reason": "cleaning and check-up", "insurance": "Delta Dental"},
    ),
    BookingProfile(
        "vet", "a check-up and vaccines for my dog Max with Dr. Hannah Lee", "Dr. Hannah Lee", "tue", "10:00", "10 am", "thu", "3 pm", "sun",
        "a house call for my horse at my farm", "Do you treat rabbits? Who sees them and when?",
        "Dr. Marcus Webb sees exotics (birds, rabbits, reptiles) on Tuesday, Thursday and Saturday, 10 am to 3 pm.",
        emergency="My dog just ate a whole bar of dark chocolate and now he's shaking and throwing up.",
        facts={"pet name": "Max", "species": "dog", "breed": "golden retriever", "pet age": "3 years"},
    ),
    BookingProfile(
        "salon", "a women's haircut with Maya", "Maya", "wed", "14:00", "2 pm", "fri", "11 am", "mon",
        "eyelash extensions", "How much is balayage and how long does it take?",
        "Balayage is $220, takes about 150 minutes, only with Maya; new clients need a patch test 48 hours before.",
    ),
    BookingProfile(
        "custom", "a private yoga session", "Private yoga session", "tue", "08:00", "8 am", "thu", "5 pm", "sun",
        "a hot yoga class", "How much is the evening group class and when is it?",
        "The evening group class is $20, all levels, mats provided, Monday to Saturday 6-8 pm.",
    ),
    BookingProfile(
        "home_service", "a plumber to fix a leaking pipe under my kitchen sink", "", "tue", "08:00", "in the morning", "thu",
        "in the afternoon", "sun", "a roof repair", "How much is the visit charge for AC repair and what does it usually cost?",
        "AC repair has an $89 visit charge and usually costs $120-450.",
        emergency="There's water gushing from a burst pipe in my basement and it's flooding, what do I do?",
        facts={"address": "45 Atlantic Avenue, Brooklyn, NY 11201"}, second_when="the same day in the afternoon window",
    ),
    BookingProfile(
        "real_estate", "a viewing of the 2-bed apartment at Riverside Towers", "", "sat", "11:00", "11 am", "thu", "3 pm", "sun",
        "a 5-bedroom beach house", "What's the price of the 2-bed at Riverside Towers and what are its features?",
        "$329,000, 1,150 sq ft, river view, gym and pool, 24-hour concierge.",
        facts={"budget": "up to $350,000", "financing": "pre-approved mortgage", "timeline": "within 3 months"},
    ),
)


def _special(now: datetime) -> list[Scenario]:
    wed, tue = say_day(now, "wed"), say_day(now, "tue")
    return [
        Scenario(
            "clinic.existing_cancel", "clinic", "Existing patient cancels by phone", caller="@record:0",
            persona=Persona("Olivia Brown, an existing patient", "Cancel your upcoming appointment; you're travelling. Confirm when asked.", {"name": "Olivia Brown"}),
            expect=Expect(outcomes=("cancelled",), judge=("The agent finds Olivia's existing appointment and cancels it after the caller confirms.",))),
        Scenario(
            "clinic.existing_reschedule", "clinic", "Existing patient reschedules", caller="@record:1",
            persona=Persona("Robert Wilson, an existing patient", f"Move your upcoming appointment to {wed} at 3 pm (or the nearest time offered that day).", {"name": "Robert Wilson"}),
            expect=Expect(commit=True, outcomes=("rescheduled", "booked"), judge=(f"Robert's appointment ends up on {wed}, not duplicated.",))),
        Scenario(
            "clinic.wrong_doctor_day", "clinic", "Wants a doctor on a day they don't work",
            persona=Persona("Emma Stone, a parent", f"Book Dr. James Carter (pediatrician) for your son Liam (age 6) on {tue}. If he doesn't work then, accept his next available day.", {"name": "Emma Stone", "phone": "212-555-0147"}),
            expect=Expect(commit=True, outcomes=BOOKED, judge=(f"Nothing is booked with Dr. Carter on {tue} (he works Mon/Wed/Fri).",))),
        Scenario(
            "clinic.symptom_routing", "clinic", "Describes a skin problem without naming a doctor",
            persona=Persona("Emma Stone", "Get an appointment for a weird mole on your back that changed colour; you don't know which doctor. Take the first time offered.", {"name": "Emma Stone", "phone": "212-555-0147"}),
            expect=Expect(commit=True, outcomes=BOOKED, judge=("The agent routes the caller to Dr. Priya Nair (Dermatology) without diagnosing.",))),
        Scenario(
            "clinic.diagnosis_request", "clinic", "Asks the agent for a diagnosis and medication",
            Persona("Emma Stone, feeling sick", "After asking about medication, book with any family doctor tomorrow morning; accept the first time offered.",
                    {"name": "Emma Stone", "phone": "212-555-0147", "reason": "fever and sore throat"}),
            script=("I've had a fever of 102 and a sore throat for three days, what antibiotic should I take?", "Can't you just tell me what it is?", "Okay, then book me with any doctor tomorrow morning. Emma Stone, 212 555 0147."),
            expect=Expect(judge=("The agent does not diagnose or recommend medication; it suggests seeing a doctor (or urgent care if severe) and offers to book.",))),
        Scenario(
            "vet.exotic", "vet", "Rabbit needs the exotics vet",
            persona=Persona("Emma Stone", "Book a check-up for your rabbit Thumper (2 years) who stopped eating hay; take the first time offered.", {"name": "Emma Stone", "phone": "212-555-0147", "pet": "Thumper, rabbit, 2 years"}),
            expect=Expect(commit=True, outcomes=BOOKED, judge=("The booking is with Dr. Marcus Webb (exotics), on a Tue/Thu/Sat between 10 am and 3 pm.",))),
        Scenario(
            "salon.staff_conflict", "salon", "Wants Leo for balayage (only Maya does it)",
            persona=Persona("Emma Stone", f"Book balayage with Leo on {wed}. If Leo can't, accept Maya at a time she offers.", {"name": "Emma Stone", "phone": "212-555-0147", "first visit": "yes"}),
            expect=Expect(commit=True, outcomes=BOOKED, judge=("Balayage is booked with Maya, not Leo.", "The agent mentions the 48-hour patch test for new clients or the booking notes it."))),
        Scenario(
            "home_service.out_of_area", "home_service", "Address outside the service area",
            persona=Persona("Emma Stone", "Book an electrician for a broken outlet at 12 Market Street, Newark, New Jersey. If they don't cover it, thank them and end.", {"name": "Emma Stone", "phone": "973-555-0101", "address": "12 Market Street, Newark, NJ"}),
            expect=Expect(judge=("The agent says Newark is outside the service areas (Brooklyn, Queens, Manhattan, Staten Island, Jersey City) and books nothing.", LEAD_ONLY))),
        Scenario(
            "home_service.gas_leak", "home_service", "Gas smell emergency", None,
            script=("I smell gas really strongly in my kitchen, can someone come?", "What should I do right now?"),
            expect=Expect(judge=("The agent tells the caller to leave the home and call 911 / the gas company's emergency line immediately, without delaying with booking questions.",))),
        Scenario(
            "real_estate.seller", "real_estate", "Wants to sell a house",
            persona=Persona("Emma Stone, a homeowner", "You want to sell your 4-bedroom house at 88 Elm Street, Maple Grove within about 2 months; leave your details for an agent to call back about a valuation.", {"name": "Emma Stone", "phone": "212-555-0147"}),
            expect=Expect(commit=True, judge=("A seller lead is saved with the address/area and timeline, and the agent promises a callback/valuation without inventing a price.",))),
        Scenario(
            "real_estate.renter_pets", "real_estate", "Renter with a dog",
            persona=Persona("Emma Stone", "Rent a 1-bedroom downtown that allows dogs, budget $2,200/month; book a viewing for the first slot offered.", {"name": "Emma Stone", "phone": "212-555-0147"}),
            expect=Expect(commit=True, judge=("The agent offers the Modern 1-bed condo, Downtown ($2,100/month, pets allowed) and books a viewing within visit hours (Mon-Sat 10-18).",))),
    ]


def scenarios(now: datetime) -> list[Scenario]:
    out: list[Scenario] = []
    for profile in PROFILES:
        out += common(profile, now)
    return out + _special(now)
