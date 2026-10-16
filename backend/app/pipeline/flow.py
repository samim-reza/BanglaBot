"""PipelineFlow: a conversation flow assembled from skills instead of a hand-written cascade.

``next_stage`` walks the outbound identity gate → the prelude (intent router)
→ the active branch's enabled skills in the account's order → the branch tail
(read-back → commit). The first skill that applies and still needs something
owns the turn: its line is spoken, its goal is the model's directive. A skill
whose slots are filled — volunteered, derived or pre-filled — is skipped.

Vertical subclasses supply what is genuinely theirs: prompt rules and facts,
the read-back summary, the commit, and the outcome lines.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.flows.base import (
    OUTCOME_BOOKED,
    OUTCOME_RESCHEDULED,
    STAGE_COMMIT,
    STAGE_DONE,
    CommitAction,
    Instruction,
    Terminal,
)
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import CONFIRMED, DECISION, STAGE_AMEND, STAGE_CONFIRM, StepFlow
from app.pipeline.blueprint import TAIL_COMMIT, TAIL_NONE, Branch
from app.pipeline.followup import AFTER, AMEND, PipelineFollowUpMixin, RecordView
from app.pipeline.lines import PipelineLinesMixin
from app.pipeline.tools import PipelineToolsMixin
from app.skills.base import DECLINED, BoundSkill
from app.verticals.common import clear_notice, with_notice
from app.voice.languages import normalize_language, phrase


def join(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _no_blank_name(text: str) -> str:
    """A read-back with a detail the caller declined: "for , Tuesday" → "for you, Tuesday";
    "4-bedroom, asking ." → "4-bedroom."; empty clauses (", ,") disappear."""
    text = re.sub(r"\bfor\s*,", "for you,", text)
    text = re.sub(r"\bfor\s*\.", "for you.", text)
    text = re.sub(r",\s*(?:asking|in|at|with|on|about)\s*(?=[.,])", "", text)
    text = re.sub(r"(?:,\s*)+(?=[,.])", "", text)
    return re.sub(r"^So,\s*,\s*", "So, ", re.sub(r"\s+,", ",", text))


class PipelineFlow(PipelineFollowUpMixin, PipelineToolsMixin, PipelineLinesMixin, StepFlow):
    def __init__(self, compiled: Any) -> None:
        self.cp = compiled
        bp = compiled.blueprint
        self.key = bp.key
        self.vertical = bp.vertical
        self.direction = bp.direction
        self.identity_gate = bp.direction != DIRECTION_INBOUND
        self.slot_specs = compiled.slot_specs
        self.yes_no_stages = {STAGE_CONFIRM: CONFIRMED, **compiled.yes_no_stages}
        self.stage_slots = dict(compiled.stage_slots)
        self.long_answer_stages = compiled.long_answer_stages
        self.passive_slots = frozenset({"note", *compiled.passive})
        self.date_slots = compiled.date_slots or ("date",)

    @property
    def gated_slots(self) -> tuple[str, ...]:  # type: ignore[override]
        return (*self.cp.gated, CONFIRMED)

    # ---- where are we -------------------------------------------------------------------
    @property
    def blueprint(self):  # noqa: ANN201
        return self.cp.blueprint

    def branch(self, slots: dict[str, Any]) -> Branch | None:
        chosen = self.blueprint.branch_of(slots)
        return chosen if chosen is not None and chosen.key in self.cp.branches else None

    def active(self, slots: dict[str, Any]) -> list[BoundSkill]:
        """Prelude + the chosen branch's enabled skills + globals, in order."""
        branch = self.branch(slots)
        skills = [*self.cp.prelude, *(self.cp.branches[branch.key] if branch else ()), *self.cp.globals]
        return list({b.key: b for b in skills}.values())

    def owner(self, stage: str, slots: dict[str, Any]) -> BoundSkill | None:
        for bound in (*self.active(slots), *self.cp.sequence()):
            if stage in bound.skill.stages(bound):
                return bound
        return None

    def skill_for_slot(self, key: str, slots: dict[str, Any]) -> BoundSkill | None:
        for bound in (*self.active(slots), *self.cp.sequence()):
            if key in bound.skill.slot_keys(bound):
                return bound
        return None

    def step_position(self, stage: str, slots: dict[str, Any]) -> tuple[int, int]:
        """(n, total) of the owning skill among the asking skills of the active path."""
        path = [b for b in self.active(slots) if b.skill.kind in ("ask", "gate", "router")]
        owner = self.owner(stage, slots)
        index = next((i for i, b in enumerate(path) if owner is not None and b.key == owner.key), len(path))
        return index + 1, len(path) + 1

    # ---- slots ---------------------------------------------------------------------------
    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        for bound in self.cp.sequence():
            for key, value in bound.skill.initial(bound, ctx).items():
                slots.setdefault(key, value)
        return slots

    def normalize(self, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        fields = dict(fields)
        self._amend_last(fields, slots, ctx)
        override: Instruction | None = None
        done: set[str] = set()
        for bound in (*self.active(slots), *self.cp.sequence()):
            keys = [key for key in bound.skill.slot_keys(bound) if key in fields and key not in done]
            if not keys:
                continue
            done.update(keys)
            part = {key: fields.pop(key) for key in keys}
            accepted, instruction = bound.skill.normalize(bound, part, slots, ctx, language)
            fields.update(accepted)
            override = override or instruction
        return fields, override

    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        clear_notice(slots)
        super().on_saved(saved, slots, ctx)
        for bound in self.cp.sequence():
            bound.skill.on_saved(bound, saved, slots, ctx)

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        for bound in self.active(slots):
            bound.skill.derive(bound, slots, ctx)

    # ---- the cascade ---------------------------------------------------------------------------
    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        gate = self.identity_stage(slots)
        if gate is not None:
            return gate
        if slots.get(DECISION):
            return self.tail(slots)
        for bound in self.cp.prelude:
            if bound.skill.applies(bound, slots, ctx):
                stage = bound.skill.stage(bound, slots, ctx)
                if stage:
                    return stage
        branch = self.branch(slots)
        if branch is None:
            return STAGE_DONE
        declined = set(slots.get(DECLINED) or ())
        for bound in self.cp.branches[branch.key]:
            if not bound.skill.applies(bound, slots, ctx):
                continue
            stage = bound.skill.stage(bound, slots, ctx)
            if stage and stage not in declined:
                return stage
        if branch.tail == TAIL_NONE:
            return STAGE_DONE
        if branch.tail == TAIL_COMMIT:
            return STAGE_COMMIT
        return self.tail(slots)

    # ---- lines ---------------------------------------------------------------------------------
    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        lang = normalize_language(language)
        if stage == STAGE_CONFIRM:
            return with_notice(slots, ctx, lang, self.readback(slots, ctx, lang))
        bound = self.owner(stage, slots)
        line = bound.skill.line(bound, stage, slots, ctx, lang) if bound else ""
        if isinstance(line, Instruction):
            return line
        return with_notice(slots, ctx, lang, line)

    def readback(self, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        summary, question = self.readback_core(slots, ctx, language)
        parts = [bound.skill.readback_part(bound, slots, ctx, language) for bound in self.active(slots)]
        return _no_blank_name(join(summary, *parts, question))

    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        """(summary, question) of the read-back — the vertical's own words."""
        return "", phrase("confirm_reprompt", language)

    def node_directive(self, node: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if node in (STAGE_CONFIRM, STAGE_AMEND):
            return super().node_directive(node, slots, ctx, language)
        bound = self.owner(node, slots)
        goal = bound.skill.brief(bound, node, slots, ctx) if bound else ""
        if not goal:
            return ""
        expected = self.stage_slots.get(node)
        tail = f" Save with save_details: {', '.join(expected)}." if expected else ""
        return f"[STEP: {node}] {goal}{tail}"

    def fast_fields(self, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        fields = super().fast_fields(stage, text, labels, slots, ctx)
        if fields:
            return fields
        bound = self.owner(stage, slots)
        return bound.skill.fast_fields(bound, stage, text, labels, slots, ctx) if bound else None

    def slot_aliases(self) -> dict[str, str]:
        """Keys small models invent → this pipeline's real slot (only aliases whose target exists)."""
        props = {spec.key for spec in self.slot_specs}
        person = next((key for key in ("customer_name", "patient_name", "caller_name", "owner_name") if key in props), "")
        candidates = {
            "name": person, "full_name": person, "caller": person, "customer": person,
            "phone_number": "phone", "mobile": "phone", "number": "phone",
            "day": "date", "time": "time_pref", "preferred_time": "time_pref",
        }
        return {alias: target for alias, target in candidates.items() if target and target in props}

    def stage_hint(self, stage: str) -> dict[str, Any]:
        return {"long_answer": stage in self.long_answer_stages}

    # ---- commit + closing ----------------------------------------------------------------------
    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        return None

    def commit_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        action = self.commit_core(self.branch(slots), slots, ctx)
        if action is None:
            return None
        details = dict(action.fields.get("details") or {})
        for bound in self.active(slots):
            extra = bound.skill.commit_details(bound, slots, ctx)
            if extra:
                details.update(extra)
                status = extra.get("_status")
                if status:
                    action.status = status
        details.pop("_status", None)
        if slots.get(AMEND):
            # Amending the record written earlier in this call: update it, don't add a second one.
            action.record_id = str(slots[AMEND])
            if action.outcome == OUTCOME_BOOKED:
                action.outcome = OUTCOME_RESCHEDULED
        details["idem"] = idempotency_key(ctx, action)
        if details:
            action.fields = {**action.fields, "details": details}
        return action

    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        """The vertical's outcome sentence without the goodbye; empty = the generic closing."""
        return ""

    def farewell(self, ctx: CallContext, language: str) -> str:
        bound = self.cp.bound.get("farewell")
        if bound is not None and bound.enabled:
            return bound.text("farewell", language, business=ctx.merchant_value("business_name", ""))
        return ""

    def closing_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        for bound in self.cp.sequence():
            owned = bound.skill.closing(bound, outcome, slots, ctx, language)
            if owned:
                return owned  # complete as written (e.g. the emergency line)
        line = self.outcome_line(outcome, slots, ctx, language)
        if not line:
            return super().closing_line(outcome, slots, ctx, language)
        return join(line, self.farewell(ctx, language))

    def closing_for(
        self, action: CommitAction, slots: dict[str, Any], ctx: CallContext, language: str, *, farewell: bool = True
    ) -> str:
        """Closing after a successful commit: outcome line + skill notes (text coming, pay link) + goodbye."""
        line = self.outcome_line(action.outcome, slots, ctx, language)
        if not line and action.outcome == OUTCOME_RESCHEDULED:
            # An amended booking: the booking sentence already states the new time.
            line = self.outcome_line(OUTCOME_BOOKED, slots, ctx, language)
        if not line and not farewell:
            line = phrase("closing_saved", language)
        if not line:
            return super().closing_line(action.outcome, slots, ctx, language)
        notes: list[str] = []
        for bound in (*self.active(slots), *self.cp.effects):
            notes += bound.skill.notes(bound, action, slots, ctx, language)
        return join(line, *notes, self.farewell(ctx, language) if farewell else "")

    def terminals(self) -> list[Terminal]:
        out: list[Terminal] = []
        for bound in self.cp.sequence():
            out += bound.skill.terminals(bound)
        return out


def idempotency_key(ctx: CallContext, action: CommitAction) -> str:
    """Same call + same outcome + same item/time → same key (a retried commit finds the first write)."""
    fields = action.fields or {}
    raw = "|".join(
        str(part)
        for part in (
            getattr(ctx.record, "id", "") or "",
            ctx.caller_number,
            action.outcome,
            action.record_id or "",
            fields.get("catalog_item_id") or "",
            fields.get("scheduled_at") or "",
            fields.get("customer_phone") or "",
            fields.get("customer_name") or "",
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


__all__ = ["AFTER", "PipelineFlow", "RecordView", "idempotency_key", "join"]
