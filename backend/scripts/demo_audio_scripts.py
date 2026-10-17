"""The scripted sample calls rendered by ``scripts.demo_audio`` for the website's "Hear it" section.

Wording follows the agent's real lines (greeting, read-back before booking, "anything else?").
``text`` is what the transcript shows; ``say`` (optional) is what the voice reads when the
written form would be spoken badly (times, prices, house numbers, "AC").
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The agent's voice on every sample.
AGENT_VOICE = "aura-2-thalia-en"


@dataclass(frozen=True)
class Turn:
    who: str  # "agent" | "caller"
    text: str
    say: str = ""


@dataclass(frozen=True)
class Sample:
    key: str
    vertical: str
    title: str
    business: str
    caller_voice: str
    result: str
    turns: tuple[Turn, ...] = field(default_factory=tuple)


def _agent(text: str, say: str = "") -> Turn:
    return Turn("agent", text, say)


def _caller(text: str, say: str = "") -> Turn:
    return Turn("caller", text, say)


_ANYTHING_ELSE = "Is there anything else I can help you with?"
_GOODBYE = _agent("Thank you, goodbye.")

SAMPLES: tuple[Sample, ...] = (
    Sample(
        key="clinic",
        vertical="clinic",
        title="Clinic appointment",
        business="CityCare Family Clinic",
        caller_voice="aura-2-apollo-en",
        result="Appointment booked · Dr. Carter · Wed 10:40 am",
        turns=(
            _agent("Hello, thank you for calling CityCare Family Clinic. How can I help you today?"),
            _caller("Hi, I'd like to book an appointment for my son with the pediatrician."),
            _agent("Of course. Dr. James Carter sees children on Mondays, Wednesdays and Fridays. Which day works best?",
                   "Of course. Doctor James Carter sees children on Mondays, Wednesdays and Fridays. Which day works best?"),
            _caller("Wednesday morning, if you have anything."),
            _agent("We have Wednesday at 10:40 in the morning. May I have the patient's name?",
                   "We have Wednesday at ten forty in the morning. May I have the patient's name?"),
            _caller("Leo Garcia."),
            _agent("Thank you. Is this Leo's first visit with us, or has he been here before?"),
            _caller("He's been there before."),
            _agent("So that's Dr. Carter for Leo Garcia, Wednesday at 10:40 am. The consultation fee is $140. Shall I book it?",
                   "So that's Doctor Carter for Leo Garcia, Wednesday at ten forty a.m. The consultation fee is "
                   "one hundred forty dollars. Shall I book it?"),
            _caller("Yes, please."),
            _agent(f"You're all set, and I'll text you the details. Please arrive a few minutes early. {_ANYTHING_ELSE}"),
            _caller("No, that's everything. Thanks!"),
            _GOODBYE,
        ),
    ),
    Sample(
        key="restaurant",
        vertical="restaurant",
        title="Restaurant pickup order",
        business="Bella Napoli Pizzeria",
        caller_voice="aura-2-luna-en",
        result="Pickup order placed · 3 items · $28.50 + tax",
        turns=(
            _agent("Hello, thank you for calling Bella Napoli. How can I help you today?"),
            _caller("Hi, I'd like to place an order for pickup."),
            _agent("Sure. What would you like?"),
            _caller("A large Margherita pizza and an order of garlic knots."),
            _agent("Got it. Anything to drink?"),
            _caller("Yeah, a two-liter Coke."),
            _agent("And what name should I put the order under?"),
            _caller("Sarah."),
            _agent("Thanks, Sarah. So that's one large Margherita, garlic knots and a two-liter Coke, for pickup, in about "
                   "20 minutes. That's $28.50 plus tax. Is everything correct so I can confirm the order?",
                   "Thanks, Sarah. So that's one large Margherita, garlic knots and a two-liter Coke, for pickup, in about "
                   "twenty minutes. That's twenty-eight fifty plus tax. Is everything correct so I can confirm the order?"),
            _caller("Yep, that's right."),
            _agent(f"Your order is confirmed. It'll be ready in about 20 minutes. {_ANYTHING_ELSE}",
                   f"Your order is confirmed. It'll be ready in about twenty minutes. {_ANYTHING_ELSE}"),
            _caller("Nope, that's it. Thank you!"),
            _GOODBYE,
        ),
    ),
    Sample(
        key="home-service",
        vertical="home_service",
        title="Home service visit",
        business="FixRight Home Services",
        caller_voice="aura-2-arcas-en",
        result="Visit booked · AC repair · tomorrow 9–12",
        turns=(
            _agent("Hello, thank you for calling FixRight Home Services. How can I help you today?"),
            _caller("Hi. My AC is blowing warm air. Can someone come take a look?",
                    "Hi. My A.C. is blowing warm air. Can someone come take a look?"),
            _agent("Sorry to hear that. What's the address for the job?"),
            _caller("418 Bergen Street, in Brooklyn.", "Four eighteen Bergen Street, in Brooklyn."),
            _agent("Thanks, we cover Brooklyn. Which day works for you?"),
            _caller("Tomorrow morning, if you can."),
            _agent("Tomorrow between 9 and 12 is open. May I have your name?",
                   "Tomorrow between nine and twelve is open. May I have your name?"),
            _caller("Mike Russo."),
            _agent("So a technician will come to 418 Bergen Street tomorrow between 9 and 12 for AC repair. The call-out "
                   "charge is $89, and the job usually costs $120 to $450, final after inspection. Shall I confirm the booking?",
                   "So a technician will come to four eighteen Bergen Street tomorrow between nine and twelve for A.C. "
                   "repair. The call-out charge is eighty-nine dollars, and the job usually costs one hundred twenty to "
                   "four hundred fifty dollars, final after inspection. Shall I confirm the booking?"),
            _caller("Yes, go ahead."),
            _agent(f"Your booking is confirmed. The technician will call before coming. {_ANYTHING_ELSE}"),
            _caller("No, that's all. Thanks."),
            _GOODBYE,
        ),
    ),
)
