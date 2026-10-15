"""Payment: off, pay at the venue, caller's choice, or online required (link by text).

The amount is always the backend's (a doctor's fee, a deposit, a fixed sum) —
never the model's. Online payment holds the booking as *pending* until the
link is paid; the payments service creates and sends the link after the commit.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill
from app.skills.library.choice import ChoiceSkill
from app.skills.library.lines import L2, line
from app.verticals.base import FieldSpec, L
from app.verticals.common import money

MODES = (
    ("off", L("No payment on the call", "কলে কোনো পেমেন্ট নয়")),
    ("at_venue", L("Pay on arrival", "এসে পেমেন্ট")),
    ("caller_choice", L("Caller chooses: online or on arrival", "কলার বেছে নেবেন")),
    ("online_required", L("Online payment required", "অনলাইন পেমেন্ট বাধ্যতামূলক")),
)
SOURCES = (
    ("fee", L("The item's price / fee", "ফি / দাম")),
    ("deposit", L("A deposit", "অগ্রিম")),
    ("fixed", L("A fixed amount", "নির্দিষ্ট অঙ্ক")),
)


class PaymentSkill(ChoiceSkill):
    key = "payment"
    slot = "payment_method"
    label = L2("Payment", "পেমেন্ট")
    description = L2("Collect payment: on arrival, online by text link, or the caller's choice.", "এসে, অনলাইন লিংকে, বা কলারের পছন্দে পেমেন্ট।")
    default_enabled = False
    options = (
        FieldSpec("mode", L("How callers pay", "পেমেন্ট পদ্ধতি"), "select", options=MODES, default="at_venue"),
        FieldSpec("amount_source", L("Amount", "অঙ্ক"), "select", options=SOURCES, default="fee"),
        FieldSpec("deposit_amount", L("Deposit", "অগ্রিম"), "money"),
        FieldSpec("fixed_amount", L("Fixed amount", "নির্দিষ্ট অঙ্ক"), "money"),
        FieldSpec("hold_minutes", L("Hold an unpaid booking (minutes)", "অপরিশোধিত বুকিং ধরে রাখা (মিনিট)"), "number", default=30),
    )
    defaults = {"mode": "at_venue", "amount_source": "fee", "hold_minutes": 30}
    slots = (SlotSpec("payment_method", "online = pay now by a texted link, at_venue = pay on arrival. Only if they choose.", {"type": "string", "enum": ["online", "at_venue"]}),)
    lines = (
        line("ask", "Would you like to pay {amount} online now by a link we text you, or pay when you arrive?", "আপনি কি এখনই অনলাইনে লিংকে {amount} পরিশোধ করবেন, নাকি এসে দেবেন?", label="Ask how to pay", variables=("amount",)),
        line("readback_venue", "The {amount} is paid when you arrive.", "{amount} এসে পরিশোধ করবেন।", label="Read-back (on arrival)", variables=("amount",)),
        line("readback_online", "We'll text you a payment link for {amount}.", "{amount} পরিশোধের লিংক এসএমএস করে পাঠাব।", label="Read-back (online)", variables=("amount",)),
        line("readback_required", "To confirm, we'll text you a payment link for {amount}; we hold the booking for {hold} minutes.", "নিশ্চিত করতে {amount} পরিশোধের লিংক এসএমএস করব; বুকিং {hold} মিনিট ধরে রাখব।", label="Read-back (online required)", variables=("amount", "hold")),
        line("closing_online", "Please pay using the link in your texts.", "এসএমএস-এর লিংক থেকে পেমেন্টটা করে নেবেন।", label="Closing (online)", static=True),
    )
    synonyms = {
        "online": ("online", "link", "now", "card", "bkash", "অনলাইন", "লিংক", "বিকাশ", "এখনই"),
        "at_venue": ("arrive", "there", "cash", "later", "on arrival", "in person", "এসে", "ক্যাশ", "পরে"),
    }
    goal = "Find out whether they pay online now (texted link) or on arrival."

    def __init__(self, key: str | None = None, *, amount: Callable[[dict[str, Any], CallContext], Any] | None = None, **overrides: Any) -> None:
        super().__init__(key, **overrides)
        self.fee = amount or (lambda slots, ctx: 0)

    # ---- amount + method ------------------------------------------------------------------------
    def amount(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> float:
        source = b.opt("amount_source", "fee")
        raw = b.opt("deposit_amount") if source == "deposit" else b.opt("fixed_amount") if source == "fixed" else self.fee(slots, ctx)
        try:
            return max(0.0, float(raw or 0))
        except (TypeError, ValueError):
            return 0.0

    def method(self, b: BoundSkill, slots: dict[str, Any]) -> str:
        mode = b.opt("mode", "at_venue")
        if mode == "online_required":
            return "online"
        if mode == "at_venue":
            return "at_venue"
        return str(slots.get("payment_method") or "")

    def validate_options(self, options: Mapping[str, Any]) -> list[tuple[str, str]]:
        source = options.get("amount_source")
        if source == "deposit" and not options.get("deposit_amount"):
            return [("deposit_amount", "set the deposit amount")]
        if source == "fixed" and not options.get("fixed_amount"):
            return [("fixed_amount", "set the amount")]
        return []

    # ---- conversation ---------------------------------------------------------------------------
    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return b.opt("mode", "at_venue") != "off" and self.amount(b, slots, ctx) > 0

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        if b.opt("mode", "at_venue") == "caller_choice" and not slots.get("payment_method"):
            return "payment_method"
        return None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("ask", language, amount=money(self.amount(b, slots, ctx), ctx, language))

    def readback_part(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if not self.applies(b, slots, ctx):
            return ""
        amount = money(self.amount(b, slots, ctx), ctx, language)
        if b.opt("mode") == "online_required":
            return b.text("readback_required", language, amount=amount, hold=int(b.opt("hold_minutes", 30) or 30))
        if self.method(b, slots) == "online":
            return b.text("readback_online", language, amount=amount)
        return b.text("readback_venue", language, amount=amount)

    def commit_details(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        if not self.applies(b, slots, ctx):
            return {"payment": {"status": "not_required"}}
        method = self.method(b, slots) or "at_venue"
        details: dict[str, Any] = {
            "payment": {
                "mode": b.opt("mode"),
                "method": method,
                "amount": self.amount(b, slots, ctx),
                "currency": ctx.currency,
                "status": "link_pending" if method == "online" else "pay_at_venue",
                "hold_minutes": int(b.opt("hold_minutes", 30) or 30),
            }
        }
        if b.opt("mode") == "online_required":
            details["_status"] = "pending"  # holds the slot until the link is paid
        return details

    def notes(self, b: BoundSkill, action, slots: dict[str, Any], ctx: CallContext, language: str) -> list[str]:  # noqa: ANN001
        return [b.text("closing_online", language)] if self.applies(b, slots, ctx) and self.method(b, slots) == "online" else []


__all__ = ["PaymentSkill"]
