"""Calls the agent makes: e-commerce order confirmations and clinic reminders, plus shop inbound."""

from __future__ import annotations

from datetime import datetime

from scripts.scenarios.dates import say_day
from scripts.scenarios.model import Expect, Persona, Scenario


def _buyer(goal: str, *, curveballs: tuple[str, ...] = (), style: str = "") -> Persona:
    kwargs = {"who": "Emily Johnson, who ordered from the online shop", "goal": goal, "facts": {"name": "Emily Johnson"}, "curveballs": curveballs}
    if style:
        kwargs["style"] = style
    return Persona(**kwargs)


def scenarios(now: datetime) -> list[Scenario]:
    thu = say_day(now, "thu")
    shop = "ecommerce"
    return [
        Scenario("ecommerce.out_confirm", shop, "Confirms the cash-on-delivery order", _buyer("Confirm the order is right and that you'll pay on delivery."),
                 direction="outbound", expect=Expect(outcomes=("confirmed",), judge=("The order is confirmed only after the customer clearly agrees.",))),
        Scenario("ecommerce.out_cancel", shop, "Cancels the order", _buyer("You changed your mind; cancel the order. Confirm the cancellation when asked."),
                 direction="outbound", expect=Expect(outcomes=("cancelled",), judge=("The order is cancelled after the customer confirms.",))),
        Scenario("ecommerce.out_question_then_confirm", shop, "Asks about the order before confirming",
                 _buyer("Before confirming, ask what exactly you ordered and the total; then confirm."),
                 direction="outbound", expect=Expect(outcomes=("confirmed",), judge=("Order details stated match the order record; it's confirmed at the end.",))),
        Scenario("ecommerce.out_later", shop, "Busy, asks for a call later", _buyer("You're driving; ask them to call back in the evening."),
                 direction="outbound", expect=Expect(commit=False, judge=("The agent agrees to call later and ends quickly without confirming or cancelling.",))),
        Scenario("ecommerce.out_wrong_person", shop, "Wrong person answers",
                 Persona("Pat Lee, who has never heard of Emily Johnson", "Say they have the wrong number; you don't know any Emily Johnson.", {"name": "Pat Lee"}),
                 direction="outbound", expect=Expect(outcomes=("wrong_number",), judge=("The agent apologises and ends; it doesn't reveal the order details to the wrong person.",))),
        Scenario("ecommerce.out_address_change", shop, "Wants to change the delivery address",
                 _buyer("Confirm the order but the delivery address must change to 77 Pine Street, Apt 4, Jersey City."),
                 direction="outbound", expect=Expect(judge=("The new address (77 Pine Street, Apt 4, Jersey City) is captured accurately for the order or a note, and the agent doesn't claim something it can't do.",))),
        Scenario("ecommerce.out_flip_flop", shop, "Confirms, then cancels, then confirms",
                 _buyer("Keep the order in the end.", curveballs=("When asked to confirm, say in ONE sentence: 'Cancel it — no wait, sorry, keep it, I do want it.'",)),
                 direction="outbound", expect=Expect(outcomes=("confirmed",), judge=("The final state is confirmed — the customer's last decision.",))),
        Scenario("ecommerce.in_status", shop, "Customer calls about an order", caller="@record:0",
                 persona=_buyer("Ask about the status of your order and when it will arrive, then say thanks."),
                 expect=Expect(judge=("The agent tells Emily her order's status from the record and invents no tracking details; "
                                      "taking a message for what it can't answer (a delivery date) is fine.",))),
        Scenario("ecommerce.in_cancel", shop, "Customer calls to cancel", caller="@record:0",
                 persona=_buyer("Cancel your order; confirm when asked."),
                 expect=Expect(judge=("The cancellation is recorded for the team: a saved message/request to cancel the order (naming it) counts — "
                                      "inbound calls pass cancellations to staff by design.",))),
        Scenario("ecommerce.in_message", shop, "Leaves a message for the shop",
                 Persona("Daniel Smith", "You received a shirt in the wrong size (M instead of L); leave a message asking for an exchange.", {"name": "Daniel Smith", "phone": "646-555-0110"}),
                 expect=Expect(judge=("A message with the exchange request (wrong size M, wants L) and the caller's name/number is taken.",))),
        Scenario("clinic.out_reminder_confirm", "clinic", "Reminder call: patient confirms", direction="outbound",
                 persona=Persona("Olivia Brown, the patient", "Confirm you'll attend your appointment.", {"name": "Olivia Brown"}),
                 expect=Expect(outcomes=("confirmed",), judge=("The appointment is confirmed after identity is confirmed.",))),
        Scenario("clinic.out_reminder_reschedule", "clinic", "Reminder call: patient needs another time", direction="outbound",
                 persona=Persona("Olivia Brown, the patient", f"You can't make it; move it to {thu} morning (take any morning time offered).", {"name": "Olivia Brown"}),
                 expect=Expect(outcomes=("rescheduled", "booked", "confirmed"), judge=(f"The appointment is moved to {thu} morning; no duplicate left at the old time.",))),
        Scenario("clinic.out_reminder_cancel", "clinic", "Reminder call: patient cancels", direction="outbound",
                 persona=Persona("Olivia Brown, the patient", "Cancel the appointment, you're feeling better.", {"name": "Olivia Brown"}),
                 expect=Expect(outcomes=("cancelled",), judge=("The appointment is cancelled after the patient confirms.",))),
    ]
