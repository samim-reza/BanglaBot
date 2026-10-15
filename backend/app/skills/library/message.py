"""Take a message for the team (anything the agent can't settle on the call)."""

from __future__ import annotations

from app.flows.steps import SlotSpec
from app.skills.base import Skill
from app.skills.library.lines import L2, line


class MessageSkill(Skill):
    key = "message"
    label = L2("Message", "বার্তা")
    description = L2("Takes a message for your team.", "আপনার টিমের জন্য বার্তা নেয়।")
    slots = (SlotSpec("message", "The caller's message for the team, in their words (short)."),)
    lines = (line("message", "Sure — what message should I pass on to the team?", "অবশ্যই — টিমকে কী বার্তা জানাব?", label="Ask for the message", static=True),)
    long_answer = frozenset({"message"})
    volunteerable = frozenset({"message"})
    goal = "Take down the caller's message for the team."


__all__ = ["MessageSkill"]
