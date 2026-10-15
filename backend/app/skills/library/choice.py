"""Base for one-of-a-few answers (new/existing, in person/online, pay now/later).

A clean, short answer that matches exactly one option's words is taken
without the model; anything else goes to the model as usual.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.flows import hearing
from app.flows.context import CallContext
from app.skills.base import BoundSkill, Skill


class ChoiceSkill(Skill):
    #: The slot holding the answer.
    slot: str = ""
    #: option → words that mean it (lower-case, any language).
    synonyms: Mapping[str, tuple[str, ...]] = {}

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return (self.slot,)

    def fast_fields(self, b: BoundSkill, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        # A short line (≤ 6 words, no question mark) naming exactly one option; anything else → the model.
        if stage != self.slot or "?" in text or not 0 < len(hearing.tokens(text)) <= 6:
            return None
        lowered = f" {text.lower()} "
        hits = [option for option, words in self.synonyms.items() if any(f" {w} " in lowered or w in lowered for w in words)]
        return {self.slot: hits[0]} if len(hits) == 1 else None


__all__ = ["ChoiceSkill"]
