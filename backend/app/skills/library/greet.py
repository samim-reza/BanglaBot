"""Greeting and goodbye: lines only, every word editable by the owner."""

from __future__ import annotations

from app.skills.base import Skill
from app.skills.library.lines import L2, line


class GreetSkill(Skill):
    key = "greet"
    kind = "line"
    toggleable = False
    label = L2("Greeting", "শুভেচ্ছা")
    description = L2("The first thing callers hear.", "কলার প্রথমে যা শোনেন।")
    lines = (
        line("greeting", "Hello, thank you for calling {business}.", "আসসালামু আলাইকুম, {business} এ ফোন করার জন্য ধন্যবাদ।", label="Greeting (phone)", variables=("business",), static=True),
        line("greeting_chat", "Hi, welcome to {business}!", "আসসালামু আলাইকুম, {business} এ স্বাগতম।", label="Greeting (chat)", variables=("business",), static=True),
        line("opening_question", "How can I help you today?", "আমি কীভাবে সাহায্য করতে পারি?", label="First question", variables=("business",), static=True),
    )


class FarewellSkill(Skill):
    key = "farewell"
    kind = "line"
    toggleable = False
    label = L2("Goodbye", "বিদায়")
    description = L2("Said at the end of every completed call.", "প্রতিটি সম্পন্ন কলের শেষে বলা হয়।")
    lines = (line("farewell", "Thank you, goodbye.", "ধন্যবাদ, ভালো থাকবেন।", label="Goodbye", variables=("business",), static=True),)


__all__ = ["FarewellSkill", "GreetSkill"]
