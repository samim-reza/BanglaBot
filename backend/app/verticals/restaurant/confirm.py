"""The restaurant's read-back and closing wording (owner-editable); the flow assembles them."""

from __future__ import annotations

from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L, line


class RestaurantConfirmSkill(Skill):
    key = "confirm"
    kind = "line"
    toggleable = False
    label = L("Read-back and closing")
    description = L("What is read back before confirming, and what is said after.")
    lines = (
        line("readback_order", "So that's {items}, {fulfillment}, {when}.", label="Order read-back", variables=("items", "fulfillment", "when")),
        line("pickup", "for pickup", label="Pickup", static=True),
        line("delivery", "for delivery to {address}", label="Delivery", variables=("address",)),
        line("ready_in", "ready in about {minutes} minutes", label="Ready in (pickup)", variables=("minutes",)),
        line("arrives_in", "arriving in about {minutes} minutes", label="Arrives in (delivery)", variables=("minutes",)),
        line("in_minutes", "in about {minutes} minutes", label="In … minutes (closing)", variables=("minutes",)),
        line("breakdown", "That's {subtotal} plus {extras}.", label="Price breakdown", variables=("subtotal", "extras")),
        line("fee", "{fee} delivery", label="Delivery fee", variables=("fee",)),
        line("tax", "{tax} tax", label="Tax", variables=("tax",)),
        line("free_delivery", "Delivery is free.", label="Free delivery", static=True),
        line("total", "Your total is {total}.", label="Total", variables=("total",)),
        line("confirm_order", "Is everything correct so I can confirm the order?", label="Confirm question (order)", static=True),
        line("readback_booking", "So that's a table for {party} {when}, under {name}.", label="Table read-back", variables=("party", "when", "name")),
        line("confirm_booking", "Shall I book it?", label="Confirm question (table)", static=True),
        line("readback_message", "So I'll pass this on to our team: {message}. They'll call you back on {phone}.", label="Message read-back", variables=("message", "phone")),
        line("confirm_message", "Is that right?", label="Confirm question (message)", static=True),
        line("closing_pickup", "Your order is confirmed — it'll be ready {when}.", label="After an order (pickup)", variables=("when",)),
        line("closing_delivery", "Your order is confirmed — it should arrive {when}.", label="After an order (delivery)", variables=("when",)),
        line("closing_booking", "Your table is booked for {when}. We look forward to seeing you.", label="After a table booking", variables=("when",)),
        line("closing_message", "Thanks, I've passed it on — our team will call you back soon.", label="After a message", static=True),
    )

    def prefetch(self, b: BoundSkill, ctx, language: str) -> list[str]:  # noqa: ANN001
        return [b.text("confirm_order", language), b.text("confirm_booking", language), b.text("closing_message", language)]


__all__ = ["RestaurantConfirmSkill"]
