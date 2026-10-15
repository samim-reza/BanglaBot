"""The restaurant's read-back and closing wording (owner-editable); the flow assembles them."""

from __future__ import annotations

from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L2, line


class RestaurantConfirmSkill(Skill):
    key = "confirm"
    kind = "line"
    toggleable = False
    label = L2("Read-back and closing", "পড়ে শোনানো ও সমাপ্তি")
    description = L2("What is read back before confirming, and what is said after.", "কনফার্মের আগে যা পড়ে শোনানো হয় ও পরে যা বলা হয়।")
    lines = (
        line("readback_order", "So that's {items}, {fulfillment}, {when}.", "তাহলে আপনার অর্ডার {items}, {fulfillment}, {when}।", label="Order read-back", variables=("items", "fulfillment", "when")),
        line("pickup", "for pickup", "পিকআপ", label="Pickup", static=True),
        line("delivery", "for delivery to {address}", "ডেলিভারি হবে {address} এ", label="Delivery", variables=("address",)),
        line("ready_in", "ready in about {minutes} minutes", "প্রায় {minutes} মিনিটে রেডি হবে", label="Ready in (pickup)", variables=("minutes",)),
        line("arrives_in", "arriving in about {minutes} minutes", "প্রায় {minutes} মিনিটে পৌঁছাবে", label="Arrives in (delivery)", variables=("minutes",)),
        line("in_minutes", "in about {minutes} minutes", "প্রায় {minutes} মিনিটের মধ্যে", label="In … minutes (closing)", variables=("minutes",)),
        line("breakdown", "That's {subtotal} plus {extras}.", "খাবার {subtotal}, সাথে {extras}।", label="Price breakdown", variables=("subtotal", "extras")),
        line("fee", "{fee} delivery", "ডেলিভারি চার্জ {fee}", label="Delivery fee", variables=("fee",)),
        line("tax", "{tax} tax", "ট্যাক্স {tax}", label="Tax", variables=("tax",)),
        line("free_delivery", "Delivery is free.", "ডেলিভারি ফ্রি।", label="Free delivery", static=True),
        line("total", "Your total is {total}.", "মোট {total}।", label="Total", variables=("total",)),
        line("confirm_order", "Is everything correct so I can confirm the order?", "সব ঠিক আছে? অর্ডারটা কনফার্ম করব?", label="Confirm question (order)", static=True),
        line("readback_booking", "So that's a table for {party} {when}, under {name}.", "তাহলে {when} {party} জনের টেবিল, {name} এর নামে।", label="Table read-back", variables=("party", "when", "name")),
        line("confirm_booking", "Shall I book it?", "বুক করব?", label="Confirm question (table)", static=True),
        line("readback_message", "So I'll pass this on to our team: {message}. They'll call you back on {phone}.", "তাহলে আমাদের টিমকে জানাচ্ছি: {message}। তারা {phone} নম্বরে ফোন করবে।", label="Message read-back", variables=("message", "phone")),
        line("confirm_message", "Is that right?", "ঠিক আছে?", label="Confirm question (message)", static=True),
        line("closing_pickup", "Your order is confirmed — it'll be ready {when}.", "আপনার অর্ডার কনফার্ম হয়েছে — {when} রেডি হবে।", label="After an order (pickup)", variables=("when",)),
        line("closing_delivery", "Your order is confirmed — it should arrive {when}.", "আপনার অর্ডার কনফার্ম হয়েছে — {when} পৌঁছে যাবে।", label="After an order (delivery)", variables=("when",)),
        line("closing_booking", "Your table is booked for {when}. We look forward to seeing you.", "আপনার টেবিল বুক হয়েছে — {when}। আপনার অপেক্ষায় থাকলাম।", label="After a table booking", variables=("when",)),
        line("closing_message", "Thanks, I've passed it on — our team will call you back soon.", "ধন্যবাদ, জানিয়ে দিয়েছি — আমাদের টিম শীঘ্রই ফোন করবে।", label="After a message", static=True),
    )

    def prefetch(self, b: BoundSkill, ctx, language: str) -> list[str]:  # noqa: ANN001
        return [b.text("confirm_order", language), b.text("confirm_booking", language), b.text("closing_message", language)]


__all__ = ["RestaurantConfirmSkill"]
