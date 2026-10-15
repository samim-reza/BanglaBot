"""Fuzzy, phonetic matching of what a caller said to menu names ("peperoni pizza" → Pepperoni Pizza).

Scores (0–100), after lower-casing, dropping filler words and singularising:

    100  same name (or alias)
     80  every word the caller said is in the name ("pepperoni" → "Pepperoni Pizza")
     77  every word they said is nearly in the name (spelling or sound-alike: "margarita" ~ "Margherita")
     75  every word of the name is in what they said ("large pepperoni pizza")
     65  one contains the other
  45–70  some words match ("garlic toast" ~ "Garlic Bread")

A unique best score of 75+ is a match; 45–74 is a "did you mean …?"; ties are a choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Generic, Iterable, TypeVar

T = TypeVar("T")

MATCH = 75
SUGGEST = 45
_FILLER = frozenset({"a", "an", "the", "of", "please", "some", "one", "order", "x", "with", "and"})
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _singular(token: str) -> str:
    if not token.isascii():
        return token
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


@lru_cache(maxsize=4096)
def norm(text: str) -> str:
    words = _WORD.findall(str(text or "").lower().replace("&", " and "))
    return " ".join(_singular(word) for word in words if word not in _FILLER)


@lru_cache(maxsize=4096)
def phonetic(token: str) -> str:
    """A rough sound key for Latin-script words: similar-sounding spellings share it."""
    if not token.isascii() or not token.isalpha():
        return token
    text = token.lower()
    for old, new in (("ph", "f"), ("ck", "k"), ("qu", "k"), ("q", "k"), ("x", "ks"), ("z", "s"), ("dg", "j")):
        text = text.replace(old, new)
    text = re.sub(r"c(?=[eiy])", "s", text).replace("c", "k")
    head, rest = text[0], re.sub(r"[aeiouyhw]", "", text[1:])
    key = head
    for ch in rest:
        if ch != key[-1]:
            key += ch
    return key


def _similar(a: str, b: str) -> float:
    if a == b:
        return 1.0
    key = phonetic(a)
    if len(key) >= 3 and key == phonetic(b):  # short keys ("coke" → "k") would match too much
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def score(query: str, target: str) -> int:
    """How well ``query`` (already normalised) names ``target`` (already normalised)."""
    if not query or not target:
        return 0
    if query == target:
        return 100
    q, t = query.split(), target.split()
    if set(q) <= set(t):
        return 80
    if set(t) <= set(q):
        return 75
    if query in target or target in query:
        return 65
    near = lambda words, others: sum(1 for w in words if max((_similar(w, o) for o in others), default=0.0) >= 0.72)  # noqa: E731
    matched = near(q, t)
    if matched == len(q):
        return 77  # every word they said is (nearly) in the name: "peperoni" → Pepperoni Pizza
    if near(t, q) == len(t):
        return 75  # the whole name is (nearly) in what they said: "large peperoni pizza"
    if matched and matched >= max(1, min(len(q), len(t)) - 1):
        return min(70, 45 + matched * 12)
    return 0


@dataclass
class Found(Generic[T]):
    #: ok | choose | suggest | none
    status: str
    best: T | None = None
    choices: list[T] = field(default_factory=list)


def best_match(query: str, candidates: Iterable[tuple[T, Iterable[str]]]) -> Found[T]:
    """Pick among ``(thing, its names)``; ``names`` are the display name plus aliases."""
    wanted = norm(query)
    scored: list[tuple[int, T]] = []
    for thing, names in candidates:
        top = max((score(wanted, norm(name)) for name in names if name), default=0)
        if top:
            scored.append((top, thing))
    if not scored:
        return Found("none")
    scored.sort(key=lambda pair: -pair[0])
    top = scored[0][0]
    tied = [thing for value, thing in scored if value == top]
    if top >= MATCH:
        return Found("ok", tied[0]) if len(tied) == 1 else Found("choose", None, tied[:4])
    if top >= SUGGEST:
        return Found("suggest", tied[0]) if len(tied) == 1 else Found("choose", None, tied[:4])
    return Found("none")


__all__ = ["MATCH", "SUGGEST", "Found", "best_match", "norm", "phonetic", "score"]
