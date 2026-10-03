"""Shared machinery for slot-filling business flows (clinic, real estate, home service).

A business flow declares its slots (:class:`SlotSpec`) and writes its stage
cascade as plain Python (``next_stage``), ending with :meth:`StepFlow.tail`:

    ... → confirm (backend reads everything back) → commit (backend writes) → done

What this base adds on top of :class:`~app.flows.base.Flow`:

- the ``save_details`` schema built from the slot specs (stable per flow, so the
  tool list stays in the cached prompt prefix);
- yes/no stages answered without the model (``yes_no_stages``) — a clean
  "হ্যাঁ"/"না" fills the stage's boolean slot straight from the hearing module;
- the read-back loop: changing any detail after the read-back clears
  ``confirmed`` so the summary is read again; a "no" at the read-back asks what
  to change (``amend``);
- one-line English directives per stage for the model, and the
  backend-owned question for every stage (spoken verbatim, TTS-cached when fixed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.flows.base import (
    STAGE_COMMIT,
    STAGE_DONE,
    STAGE_IDENTITY,
    STAGE_KNOWS_PERSON,
    Flow,
    Instruction,
)
from app.flows.context import CallContext
from app.voice.languages import normalize_language, phrase

STAGE_CONFIRM = "confirm"
STAGE_AMEND = "amend"

#: Slots the flow machinery itself uses.
CONFIRMED = "confirmed"
DECISION = "decision"


@dataclass(frozen=True)
class SlotSpec:
    key: str
    description: str
    schema: dict[str, Any] = field(default_factory=lambda: {"type": "string"})
    #: The caller's own words must carry a yes/no before this boolean is accepted.
    gated: bool = False
    #: Call directions the slot exists in (empty = both).
    directions: tuple[str, ...] = ()

    def as_property(self) -> dict[str, Any]:
        return {**self.schema, "description": self.description}


def lang_text(texts: dict[str, str] | str, language: str) -> str:
    if isinstance(texts, str):
        return texts
    lang = normalize_language(language)
    return texts.get(lang) or texts.get("en") or next(iter(texts.values()), "")


CONFIRMED_SPEC = SlotSpec(
    CONFIRMED,
    "The caller's answer to the read-back of all details: true = yes, go ahead; false = something is wrong. "
    "Only after the system read the summary back. Never true for a question or a hesitant answer.",
    {"type": "boolean"},
    gated=True,
)


class StepFlow(Flow):
    #: Slot specs, in the order they are usually asked.
    slot_specs: tuple[SlotSpec, ...] = ()
    #: stage → boolean slot a clean yes/no answers (the read-back always is one).
    yes_no_stages: dict[str, str] = {STAGE_CONFIRM: CONFIRMED}
    #: stage → English goal shown to the model when the stage starts.
    stage_goals: dict[str, str] = {}
    #: stage → slots the model should save there.
    stage_slots: dict[str, tuple[str, ...]] = {}
    #: Stages whose answer is long (address, problem): the transport waits longer.
    long_answer_stages: frozenset[str] = frozenset()
    #: Slots that, when changed, do NOT invalidate an earlier read-back.
    passive_slots: frozenset[str] = frozenset({"note"})
    #: Slots holding a YYYY-MM-DD date (checked against the caller's words).
    date_slots: tuple[str, ...] = ("date", "visit_date")

    # ---- slots --------------------------------------------------------------
    def slot_properties(self) -> dict[str, Any]:
        props = dict(super().slot_properties())
        for spec in self.slot_specs:
            if spec.directions and self.direction not in spec.directions:
                continue
            props[spec.key] = spec.as_property()
        props[CONFIRMED] = CONFIRMED_SPEC.as_property()
        props.setdefault(
            "note",
            {"type": "string", "description": "Anything else the caller asked us to pass on (short, in their words)."},
        )
        return props

    @property
    def gated_slots(self) -> tuple[str, ...]:  # type: ignore[override]
        return tuple(spec.key for spec in self.slot_specs if spec.gated) + (CONFIRMED,)

    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        changed = {key for key in saved if key not in (CONFIRMED, *self.passive_slots)}
        # A changed detail means the summary must be read again — even when the
        # same turn also said "yes" ("yes, but make it 7 pm" is not a yes to the old time).
        if changed and slots.get(CONFIRMED) is not None:
            slots[CONFIRMED] = None

    def tail(self, slots: dict[str, Any]) -> str:
        """The end of every business cascade: read back → write → done."""
        if slots.get(DECISION):
            return STAGE_DONE
        confirmed = slots.get(CONFIRMED)
        if confirmed is True:
            return STAGE_COMMIT
        if confirmed is False:
            return STAGE_AMEND
        return STAGE_CONFIRM

    # ---- fast path ------------------------------------------------------------
    def fast_fields(self, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        from app.flows import hearing

        if stage in (STAGE_IDENTITY, STAGE_KNOWS_PERSON):
            return self.identity_fast_fields(stage, text, labels)
        slot = self.yes_no_stages.get(stage)
        if not slot:
            return None
        if slot == CONFIRMED and self.confirms_cancellation(slots, ctx):
            if len(hearing.tokens(text)) > 6:
                return None
            if hearing.affirms_cancel(text):
                return {slot: True}
            if hearing.declines_cancel(text):
                return {slot: False}
            return None
        if not labels or labels & {"repeat", "later", "not_me", "wrong_number"} or hearing.looks_like_question(text):
            return None
        # Only a short, pure answer: "হ্যাঁ, কিন্তু সময়টা বদলাতে হবে" carries more than a yes.
        if not hearing.is_pure_answer(text):
            return None
        if "yes" in labels and "no" not in labels:
            return {slot: True}
        if "no" in labels and "yes" not in labels:
            return {slot: False}
        return None

    def stage_hint(self, stage: str) -> dict[str, Any]:
        return {"long_answer": stage in self.long_answer_stages}

    def reask_line(self, attempt: int, language: str) -> str:
        return phrase("yes_no_reask_2" if attempt >= 2 else "yes_no_reask_1", language)

    # ---- lines ---------------------------------------------------------------------
    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        """The question for ``stage`` (verbatim) or guidance for the model."""
        raise NotImplementedError

    def instruction(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction:
        identity = self.identity_instruction(stage, ctx, language)
        if identity is not None:
            return identity
        if stage in (STAGE_DONE, STAGE_COMMIT):
            text = (
                "আর কিছু জিজ্ঞেস করার নেই। কিছু না বলে end_call টুল কল করুন।"
                if normalize_language(language) == "bn"
                else "Nothing more to ask. Call the end_call tool without saying anything."
            )
            return Instruction(stage, text, end_call=True)
        if stage == STAGE_AMEND:
            return Instruction(stage, phrase("amend_question", language), verbatim=True)
        line = self.stage_line(stage, slots, ctx, language)
        if isinstance(line, Instruction):
            return line
        return Instruction(stage, line, verbatim=True)

    def node_directive(self, node: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        goal = self.stage_goals.get(node)
        if node in (STAGE_CONFIRM,):
            goal = goal or (
                "The system read every detail back. Save confirmed=true on a clear yes, confirmed=false on a no; "
                "if the caller changes a detail instead, save the new value (the summary is read again)."
            )
        elif node == STAGE_AMEND:
            goal = goal or "The caller said something in the summary is wrong. Save the corrected detail(s) with save_details."
        if not goal:
            return ""
        expected = self.stage_slots.get(node)
        tail = f" Save with save_details: {', '.join(expected)}." if expected else ""
        return f"[STEP: {node}] {goal}{tail}"


__all__ = ["CONFIRMED", "DECISION", "STAGE_AMEND", "STAGE_CONFIRM", "SlotSpec", "StepFlow", "lang_text"]
