"""Per-call flow runtime: the slot store + the node derived from it.

``save()`` stores what the model extracted, re-derives the stage/node and
returns the tool result the model reads (``ok`` / ``saved`` / ``instruction``).
A node change is reported through ``on_directive`` so the bridge can append the
directive as a tail system message.
"""

from __future__ import annotations

from typing import Any, Callable

import structlog

from app.flows.base import STAGE_DONE, Flow, Instruction
from app.voice.languages import normalize_language

logger = structlog.get_logger(__name__)


class FlowRuntime:
    def __init__(
        self,
        flow: Flow,
        order: Any,
        merchant: Any,
        *,
        language: str | None = None,
        on_directive: Callable[[str], None] | None = None,
    ) -> None:
        self.flow = flow
        self.order = order
        self.merchant = merchant
        self.language = normalize_language(language or getattr(merchant, "language", None))
        self.on_directive = on_directive
        self.slots: dict[str, Any] = dict(flow.initial_slots(order, merchant))
        self.outcome: str = ""
        self.reasks: int = 0
        self.stage: str = flow.next_stage(self.slots, order, merchant)
        self.current_node: str = flow.node_for_stage(self.stage)
        self.directives: list[str] = []

    # ---- prompt bootstrap ----------------------------------------------------
    def greeting(self) -> str:
        return self.flow.greeting(self.merchant, self.language)

    def opening_question(self) -> str:
        return self.flow.opening_question(self.order, self.language)

    def initial_directive(self) -> str:
        return self.flow.node_directive(self.current_node, self.order, self.merchant, self.language)

    def set_language(self, language: str) -> None:
        self.language = normalize_language(language)

    # ---- the loop -------------------------------------------------------------
    def current_instruction(self) -> Instruction:
        return self.flow.instruction(self.stage, self.slots, self.order, self.merchant, self.language)

    def save(self, fields: dict[str, Any] | None) -> dict[str, Any]:
        known = self.flow.slot_properties()
        saved = {
            key: value
            for key, value in (fields or {}).items()
            if key in known and value is not None and value != ""
        }
        self.slots.update(saved)
        return self.advance(saved_keys=sorted(saved))

    def mark_decided(self, outcome: str) -> None:
        """A terminal fired: the decision slot is filled and the flow is done."""
        self.outcome = outcome
        self.slots["decision"] = outcome
        self.advance()

    def advance(self, saved_keys: list[str] | None = None) -> dict[str, Any]:
        self.stage = self.flow.next_stage(self.slots, self.order, self.merchant)
        node = self.flow.node_for_stage(self.stage)
        if node != self.current_node:
            directive = self.flow.node_directive(node, self.order, self.merchant, self.language)
            self.directives.append(directive)
            if self.on_directive is not None:
                self.on_directive(directive)
            logger.info("flow_node_transition", from_node=self.current_node, to_node=node, stage=self.stage)
            self.current_node = node
        instruction = self.current_instruction()
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
        data = {key: value for key, value in self.slots.items() if key != "decision"}
        if extra:
            data.update({key: value for key, value in extra.items() if value not in (None, "")})
        return data
