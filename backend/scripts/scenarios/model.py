"""What a scenario is: who calls, what they want, what must be true at the end."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Persona:
    """An LLM-played caller: identity, goal, the facts they know, and how they behave."""

    who: str
    goal: str
    facts: dict[str, str] = field(default_factory=dict)
    #: How they talk: "short answers", "rambles", "impatient", ...
    style: str = "Natural phone caller: one or two short sentences per turn."
    #: Twists to play at the right moment, e.g. "After the agent reads the booking back, move it to Thursday."
    curveballs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Expect:
    #: True = a record must be saved, False = nothing may be saved, None = either.
    commit: bool | None = None
    #: Accepted final outcomes (agent outcome / commit outcome); empty = any.
    outcomes: tuple[str, ...] = ()
    #: The agent must end the call / chat itself (None = don't check).
    ended: bool | None = None
    #: Scenario-specific facts the judge must confirm from the transcript + saved record.
    judge: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    vertical: str
    title: str
    persona: Persona | None = None
    #: Fixed caller turns, spoken first (before the persona takes over, if there is one).
    script: tuple[str, ...] = ()
    direction: str = "inbound"
    #: Demo record the outbound call is about.
    record: int = 0
    caller: str = "+12125550147"
    channel: str = "voice"
    #: Slots already full when the call starts: (catalog item name or "", weekday "mon".."sun", "HH:MM"),
    #: on the first such weekday after today.
    full: tuple[tuple[str, str, str], ...] = ()
    #: Slots someone else books while the call is running (the commit fails with "slot taken").
    race: tuple[tuple[str, str, str], ...] = ()
    #: Closure dates set on the business: (catalog item name or "" for the whole business, weekday, label),
    #: on the first such weekday after today.
    closed: tuple[tuple[str, str, str], ...] = ()
    max_turns: int = 18
    expect: Expect = field(default_factory=Expect)
    tags: tuple[str, ...] = ()


@dataclass
class Turn:
    role: str  # "agent" | "caller"
    text: str


@dataclass
class RunResult:
    scenario: Scenario
    turns: list[Turn] = field(default_factory=list)
    commits: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    #: Hard failures found by code (silence, crash, wrong commit ...).
    problems: list[str] = field(default_factory=list)
    #: The judge's verdict.
    verdict: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.error and not self.problems and bool(self.verdict.get("pass", True))

    def transcript(self) -> str:
        return "\n".join(f"{'AGENT' if t.role == 'agent' else 'CALLER'}: {t.text}" for t in self.turns)
