"""In person or online (video) — fixed by the owner or the caller's choice."""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.skills.base import BoundSkill
from app.skills.library.choice import ChoiceSkill
from app.skills.library.lines import L2, line
from app.verticals.base import FieldSpec, L

MODES = (
    ("caller_choice", L("Caller chooses", "কলার বেছে নেবেন")),
    ("in_person", L("In person only", "শুধু সরাসরি")),
    ("online", L("Online only", "শুধু অনলাইন")),
)


class VisitModeSkill(ChoiceSkill):
    key = "visit_mode"
    slot = "visit_mode"
    label = L2("In person or online", "সরাসরি না অনলাইন")
    description = L2("Offers an online (video) visit as well as in person.", "অনলাইন (ভিডিও) বা সরাসরি সাক্ষাৎ।")
    default_enabled = False
    options = (FieldSpec("mode", L("Visit type", "সাক্ষাতের ধরন"), "select", options=MODES, default="caller_choice"),)
    defaults = {"mode": "caller_choice"}
    slots = (SlotSpec("visit_mode", "in_person = come to the venue, online = video call. Only if they say so.", {"type": "string", "enum": ["in_person", "online"]}),)
    lines = (
        line("ask", "Would you like to come in person, or have an online video consultation?", "আপনি কি সরাসরি আসবেন, নাকি অনলাইনে ভিডিও কলে দেখাবেন?", label="Ask the visit type", static=True),
        line("readback_online", "It's an online video consultation; we'll text you the link.", "এটা অনলাইন ভিডিও কনসালটেশন; লিংকটা এসএমএস করে পাঠাব।", label="Read-back (online)", static=True),
    )
    synonyms = {
        "online": ("online", "video", "virtual", "zoom", "অনলাইন", "ভিডিও"),
        "in_person": ("in person", "come in", "visit", "physically", "সরাসরি", "চেম্বারে", "আসব"),
    }
    volunteerable = frozenset({"visit_mode"})
    goal = "Find out whether they want to come in person or have an online video visit."

    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return b.opt("mode", "caller_choice") == "caller_choice"

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        mode = b.opt("mode", "caller_choice")
        if mode != "caller_choice":
            slots["visit_mode"] = mode

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("ask", language)

    def readback_part(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return b.text("readback_online", language) if slots.get("visit_mode") == "online" else ""

    def commit_details(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        return {"visit_mode": slots.get("visit_mode") or "in_person"}

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("ask", language), b.text("readback_online", language)]


__all__ = ["VisitModeSkill"]
