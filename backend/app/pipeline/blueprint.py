"""Blueprints: which skills a vertical's call is made of, per branch.

A branch is one thing a caller can want (book, reschedule, cancel, order,
reservation, message …) and lists its skills in their default order. Owners
may reorder only inside ``movable`` groups, and ``before`` constraints always
hold (payment needs the doctor and the time first).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.skills.base import Skill

TAIL_READBACK = "readback"  # read everything back, commit on a yes
TAIL_COMMIT = "commit"  # commit without a read-back
TAIL_NONE = "none"  # nothing to write (e.g. an order-status question)


@dataclass(frozen=True)
class Branch:
    key: str
    skills: tuple[str, ...]
    label: Mapping[str, str] = field(default_factory=dict)
    #: Groups of skills the owner may reorder among themselves.
    movable: tuple[frozenset[str], ...] = ()
    #: skill → skills that must come earlier.
    before: Mapping[str, frozenset[str]] = field(default_factory=dict)
    tail: str = TAIL_READBACK
    #: The owner may switch the whole branch off (the router stops offering it).
    toggleable: bool = True

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": dict(self.label) or {"en": self.key.capitalize()},
            "skills": list(self.skills),
            "movable": [sorted(group) for group in self.movable],
            "before": {key: sorted(value) for key, value in self.before.items()},
            "tail": self.tail,
            "toggleable": self.toggleable,
        }


@dataclass(frozen=True)
class Blueprint:
    #: Same as the flow key the rest of the system knows ("clinic.inbound").
    key: str
    vertical: str
    direction: str
    skills: Mapping[str, Skill]
    version: int = 1
    #: Skills asked before any branch (e.g. the intent router).
    prelude: tuple[str, ...] = ()
    #: The slot holding the chosen branch; empty = single-branch pipeline.
    router_slot: str = ""
    branches: Mapping[str, Branch] = field(default_factory=dict)
    default_branch: str = ""
    #: Active in every branch at any time (emergency, transfer).
    globals: tuple[str, ...] = ()
    #: Run after the commit (SMS, payment link): notes in the closing, never a turn.
    effects: tuple[str, ...] = ()
    #: Spoken lines only (greeting, farewell).
    line_skills: tuple[str, ...] = ()
    #: The PipelineFlow subclass with the vertical's facts / read-back / commit.
    flow_cls: type | None = None

    def skill(self, key: str) -> Skill:
        return self.skills[key]

    def all_keys(self) -> list[str]:
        keys: list[str] = []
        for key in (*self.line_skills, *self.prelude, *self.globals):
            if key not in keys:
                keys.append(key)
        for branch in self.branches.values():
            for key in branch.skills:
                if key not in keys:
                    keys.append(key)
        for key in self.effects:
            if key not in keys:
                keys.append(key)
        return keys

    def branch_of(self, slots: Mapping[str, Any]) -> Branch | None:
        if not self.branches:
            return None
        if self.router_slot:
            chosen = self.branches.get(str(slots.get(self.router_slot) or ""))
            if chosen is not None:
                return chosen
            return None
        return self.branches.get(self.default_branch) or next(iter(self.branches.values()))

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "vertical": self.vertical,
            "direction": self.direction,
            "version": self.version,
            "prelude": list(self.prelude),
            "router_slot": self.router_slot,
            "branches": [branch.as_json() for branch in self.branches.values()],
            "default_branch": self.default_branch,
            "globals": list(self.globals),
            "effects": list(self.effects),
            "line_skills": list(self.line_skills),
            "skills": {key: self.skills[key].as_json() for key in self.all_keys()},
        }


__all__ = ["TAIL_COMMIT", "TAIL_NONE", "TAIL_READBACK", "Blueprint", "Branch"]
