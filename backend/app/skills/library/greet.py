"""Greeting and goodbye: lines only, every word editable by the owner."""

from __future__ import annotations

from app.skills.base import Skill
from app.skills.library.lines import L, line


class GreetSkill(Skill):
    key = "greet"
    kind = "line"
    toggleable = False
    label = L("Greeting")
    description = L("The first thing callers hear.")
    lines = (
        line("greeting", "Hello, thank you for calling {business}.", label="Greeting (phone)", variables=("business",), static=True),
        line("greeting_chat", "Hi, welcome to {business}!", label="Greeting (chat)", variables=("business",), static=True),
        line("opening_question", "How can I help you today?", label="First question", variables=("business",), static=True),
    )


class FarewellSkill(Skill):
    key = "farewell"
    kind = "line"
    toggleable = False
    label = L("Goodbye")
    description = L("Said at the end of every completed call.")
    lines = (line("farewell", "Thank you, goodbye.", label="Goodbye", variables=("business",), static=True),)


__all__ = ["FarewellSkill", "GreetSkill"]
