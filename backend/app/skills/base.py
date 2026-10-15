"""Skills: the "sub-agents" a call pipeline is made of.

A :class:`Skill` owns ONE task of a call — find the doctor, take the patient's
details, agree a time, settle payment, get consent — with everything that task
needs: the slots it fills, the questions it asks (owner-editable
:class:`LineSpec` lines), its options (owner-editable :class:`FieldSpec`
fields), a one-line goal for the model, and hooks to validate, derive and
commit. A skill whose slots are already filled (the caller volunteered them,
caller ID supplied them, the backend derived them) returns no stage and is
*skipped*.

Skills are stateless and shared by every call with the same configuration:
per-call state lives in the slots (``_``-prefixed keys for bookkeeping).
Bound to an account's options and lines they become a :class:`BoundSkill`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.flows.base import CommitAction, Instruction, Terminal
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.verticals.base import FieldSpec
from app.voice.languages import normalize_language

#: Bump when a skill's behaviour changes so compiled pipelines are rebuilt.
SKILL_LIB_VERSION = 1

_VAR = re.compile(r"\{([a-z_][a-z0-9_]{0,30})\}")


def template_vars(text: str) -> set[str]:
    return set(_VAR.findall(str(text or "")))


def render(template: str, values: Mapping[str, Any]) -> str:
    """Fill ``{name}`` placeholders by plain lookup.

    Owner-edited lines are never passed to ``str.format`` (``{x.__class__}``
    would reach into objects); unknown names render empty.
    """
    filled = _VAR.sub(lambda match: str(values.get(match.group(1), "") or ""), str(template or ""))
    return " ".join(filled.split())


def lang_pick(texts: Mapping[str, str] | str, language: str) -> str:
    if isinstance(texts, str):
        return texts
    lang = normalize_language(language)
    return texts.get(lang) or texts.get("en") or next(iter(texts.values()), "")


@dataclass(frozen=True)
class LineSpec:
    """A spoken line the owner may reword (per language)."""

    key: str
    default: Mapping[str, str]
    label: str = ""
    #: Placeholders the line may use, e.g. ``("doctor", "schedule")``.
    variables: tuple[str, ...] = ()
    #: Placeholders that must stay (an emergency line must keep ``{emergency}``).
    required_vars: tuple[str, ...] = ()
    max_chars: int = 300
    #: Uses only account-level values → pre-synthesised when the flow is saved.
    account_static: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label or self.key.replace("_", " ").capitalize(),
            "default": dict(self.default),
            "variables": list(self.variables),
            "required_vars": list(self.required_vars),
            "max_chars": self.max_chars,
        }


@dataclass(frozen=True)
class BoundSkill:
    """A skill with one account's settings applied (compiled; shared by calls)."""

    skill: "Skill"
    enabled: bool = True
    opts: Mapping[str, Any] = field(default_factory=dict)
    #: Owner overrides: language → line key → text.
    lines: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.skill.key

    def opt(self, name: str, default: Any = None) -> Any:
        value = self.opts.get(name)
        return default if value is None else value

    def line_text(self, key: str, language: str) -> str:
        lang = normalize_language(language)
        override = (self.lines.get(lang) or {}).get(key)
        if override:
            return override
        spec = self.skill.line_spec(key)
        return lang_pick(spec.default, lang) if spec else ""

    def text(self, key: str, language: str, **values: Any) -> str:
        return render(self.line_text(key, language), values)


class Skill:
    """Base skill. Subclasses set the class attributes and override hooks."""

    key: str = ""
    #: ask | gate (yes/no) | router | effect (after commit) | line (spoken text only) | global (any time)
    kind: str = "ask"
    label: Mapping[str, str] = {}
    description: Mapping[str, str] = {}
    slots: tuple[SlotSpec, ...] = ()
    lines: tuple[LineSpec, ...] = ()
    options: tuple[FieldSpec, ...] = ()
    defaults: Mapping[str, Any] = {}
    #: The owner may switch it off.
    toggleable: bool = True
    default_enabled: bool = True
    #: stage → boolean slot a clean yes/no fills without the model.
    yes_no: Mapping[str, str] = {}
    #: Stages whose answers are long (the transport waits longer).
    long_answer: frozenset[str] = frozenset()
    #: Slots that, when changed, do not invalidate an earlier read-back.
    passive: frozenset[str] = frozenset()
    #: Slots holding a YYYY-MM-DD date.
    date_slots: tuple[str, ...] = ()
    #: Boolean slots that need the caller's own yes/no.
    gated: tuple[str, ...] = ()
    #: Slots the model may fill in any step (volunteered details).
    volunteerable: frozenset[str] = frozenset()
    #: One-line English goal shown to the model while the skill is active.
    goal: str = ""

    def __init__(self, key: str | None = None, **overrides: Any) -> None:
        if key:
            self.key = key
        for name, value in overrides.items():
            if not hasattr(type(self), name):
                raise TypeError(f"{type(self).__name__} has no attribute {name!r}")
            setattr(self, name, value)

    # ---- declaration helpers ------------------------------------------------------
    def line_spec(self, key: str) -> LineSpec | None:
        return next((spec for spec in self.lines if spec.key == key), None)

    def slot_specs(self, b: BoundSkill | None = None) -> tuple[SlotSpec, ...]:
        """The slots this skill fills for one account (custom intake fields vary per account)."""
        return self.slots

    def slot_keys(self, b: BoundSkill | None = None) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.slot_specs(b))

    def required(self, b: BoundSkill) -> tuple[str, ...]:
        """Slots that must be filled before the skill is done (default: all of them)."""
        return self.slot_keys(b)

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        """Every stage this skill may return (for routing lines and directives)."""
        return (*self.required(b), *self.yes_no)

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "label": dict(self.label) or {"en": self.key.replace("_", " ").capitalize()},
            "description": dict(self.description),
            "toggleable": self.toggleable,
            "default_enabled": self.default_enabled,
            "options": [spec.as_json() for spec in self.options],
            "defaults": dict(self.defaults),
            "lines": [spec.as_json() for spec in self.lines],
        }

    # ---- conversation hooks ----------------------------------------------------------
    def applies(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> bool:
        return True

    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        """The next thing this skill still needs, or ``None`` when done (= skipped)."""
        for key in self.required(b):
            if slots.get(key) in (None, ""):
                return key
        return None

    def initial(self, b: BoundSkill, ctx: CallContext) -> dict[str, Any]:
        return {}

    def normalize(
        self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str
    ) -> tuple[dict[str, Any], Instruction | None]:
        return fields, None

    def on_saved(self, b: BoundSkill, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        return None

    def derive(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> None:
        return None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        return b.text(stage, language)

    def brief(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext) -> str:
        return self.goal

    def facts(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        """Business facts the model needs only while this skill is active (compact prompts)."""
        return []

    def fast_fields(
        self, b: BoundSkill, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext
    ) -> dict[str, Any] | None:
        return None

    # ---- read-back / commit / closing --------------------------------------------------
    def readback_part(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return ""

    def commit_details(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        return {}

    def notes(self, b: BoundSkill, action: CommitAction, slots: dict[str, Any], ctx: CallContext, language: str) -> list[str]:
        """Sentences spoken after the outcome line, before the goodbye."""
        return []

    def terminals(self, b: BoundSkill) -> list[Terminal]:
        return []

    def tools(self, b: BoundSkill) -> list[dict[str, Any]]:
        """Extra tool schemas (Chat Completions shape) this skill brings, e.g. a cart editor."""
        return []

    def run_tool(
        self, b: BoundSkill, name: str, args: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str, *, caller_text: str = ""
    ) -> dict[str, Any]:
        """Run one of :meth:`tools`: ``{"ok": True, "updates": {slot: value}, "say": "…"}`` or ``{"ok": False, "reason": …}``."""
        return {"ok": False, "reason": "unknown_tool"}

    def closing(self, b: BoundSkill, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        """A skill-owned closing line for ``outcome`` (e.g. the emergency line); empty = not mine."""
        return ""

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        """Fixed lines worth having in the TTS cache before a call needs them."""
        return []


__all__ = ["SKILL_LIB_VERSION", "BoundSkill", "LineSpec", "Skill", "lang_pick", "render", "template_vars"]
