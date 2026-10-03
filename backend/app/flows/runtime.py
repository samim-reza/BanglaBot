"""Per-call flow runtime: the slot store + the stage/node derived from it.

``save()`` validates what the model extracted (through the flow), stores it,
re-derives the stage and returns the tool result the model reads
(``ok`` / ``saved`` / ``stage`` / ``instruction``). A node change is reported
through ``on_directive`` so the agent can append the directive as a tail
system message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import structlog

from app.flows.base import STAGE_DONE, Flow, Instruction
from app.flows.context import CallContext
from app.voice.languages import normalize_language

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Preview:
    stage: str
    instruction: Instruction


class FlowRuntime:
    def __init__(
        self,
        flow: Flow,
        ctx: CallContext,
        *,
        language: str | None = None,
        on_directive: Callable[[str], None] | None = None,
    ) -> None:
        self.flow = flow
        self.ctx = ctx
        self.language = normalize_language(language or ctx.merchant_value("language", None))
        self.on_directive = on_directive
        self.slots: dict[str, Any] = dict(flow.initial_slots(ctx))
        self.outcome: str = ""
        self.reasks: int = 0
        self.flow.derive(self.slots, ctx)
        self.stage: str = flow.next_stage(self.slots, ctx)
        self.current_node: str = flow.node_for_stage(self.stage)
        self.directives: list[str] = []
        self._override: Instruction | None = None
        #: The instruction the last save/advance produced (what to say next).
        self.last_instruction: Instruction | None = None

    # ---- e-commerce vocabulary ---------------------------------------------------
    @property
    def order(self) -> Any:
        return self.ctx.record

    @property
    def merchant(self) -> Any:
        return self.ctx.merchant

    # ---- prompt bootstrap ----------------------------------------------------
    def greeting(self) -> str:
        return self.flow.greeting(self.ctx, self.language)

    def opening_question(self) -> str:
        return self.flow.opening_question(self.ctx, self.language)

    def opening(self) -> str:
        return self.flow.opening(self.ctx, self.language)

    def initial_directive(self) -> str:
        return self.flow.node_directive(self.current_node, self.slots, self.ctx, self.language)

    def set_language(self, language: str) -> None:
        self.language = normalize_language(language)

    # ---- the loop -------------------------------------------------------------
    def current_instruction(self) -> Instruction:
        if self._override is not None:
            return self._override
        return self.flow.instruction(self.stage, self.slots, self.ctx, self.language)

    def known_fields(self, fields: dict[str, Any] | None) -> dict[str, Any]:
        known = self.flow.slot_properties()
        return {
            key: value
            for key, value in (fields or {}).items()
            if key in known and value is not None and value != ""
        }

    def preview(self, fields: dict[str, Any]) -> Preview:
        """Where saving ``fields`` would lead, without touching the runtime."""
        slots = dict(self.slots)
        accepted, override = self.flow.normalize(self.known_fields(fields), slots, self.ctx, self.language)
        slots.update(accepted)
        self.flow.on_saved(accepted, slots, self.ctx)
        self.flow.derive(slots, self.ctx)
        stage = self.flow.next_stage(slots, self.ctx)
        return Preview(stage=stage, instruction=override or self.flow.instruction(stage, slots, self.ctx, self.language))

    def save(self, fields: dict[str, Any] | None) -> dict[str, Any]:
        accepted, override = self.flow.normalize(self.known_fields(fields), self.slots, self.ctx, self.language)
        self.slots.update(accepted)
        self.flow.on_saved(accepted, self.slots, self.ctx)
        result = self.advance(saved_keys=sorted(accepted), override=override)
        rejected = sorted(set(self.known_fields(fields)) - set(accepted))
        if rejected:
            result["not_saved"] = rejected
        return result

    def mark_decided(self, outcome: str) -> None:
        """A terminal fired: the decision slot is filled and the flow moves on."""
        self.outcome = outcome
        self.slots["decision"] = outcome
        self.advance()

    def advance(self, saved_keys: list[str] | None = None, override: Instruction | None = None) -> dict[str, Any]:
        self.flow.derive(self.slots, self.ctx)
        self.stage = self.flow.next_stage(self.slots, self.ctx)
        node = self.flow.node_for_stage(self.stage)
        if node != self.current_node:
            directive = self.flow.node_directive(node, self.slots, self.ctx, self.language)
            if directive:
                self.directives.append(directive)
                if self.on_directive is not None:
                    self.on_directive(directive)
            logger.info("flow_node_transition", flow=self.flow.key, from_node=self.current_node, to_node=node, stage=self.stage)
            self.current_node = node
        self._override = override
        instruction = self.current_instruction()
        self._override = None
        self.last_instruction = instruction
        return {
            "ok": True,
            "saved": saved_keys or [],
            "stage": self.stage,
            "instruction": instruction.for_model(self.language),
        }

    @property
    def done(self) -> bool:
        return self.stage == STAGE_DONE

    # ---- persistence ------------------------------------------------------------
    def flow_data(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        data = {
            key: value
            for key, value in self.slots.items()
            if key != "decision" and not key.startswith("_") and value not in (None, "")
        }
        if extra:
            data.update({key: value for key, value in extra.items() if value not in (None, "")})
        return data
