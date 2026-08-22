"""Per-call flow runtime: slots + derived current node.

Mirrors SloancodeAI's live engine: `advance()` recomputes the node from the
slots after every save; a node change appends a Bengali "ধাপ পরিবর্তন"
directive to the tail of the conversation context (never rewriting the
system prompt), and the returned instruction carries the backend-owned
wording of the next question.

`context` only needs an `add_message({"role": ..., "content": ...})` method
(pipecat's LLMContext has one); tests pass a stub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from app.flows.base import Flow, build_node_directive_bn

if TYPE_CHECKING:  # pragma: no cover
    from app.models import Merchant, Order


class FlowRuntime:
    def __init__(self, flow: Flow, order: "Order", merchant: "Merchant", context: Any = None):
        self.flow = flow
        self.order = order
        self.merchant = merchant
        self.context = context
        self.settings = flow.merged_settings(merchant)
        self.slots: dict[str, Any] = flow.initial_slots(order, merchant, self.settings)
        self.stage = flow.next_missing_stage(self.slots, self.settings, order)
        self.current_node = flow.node_for_stage(self.stage)

    # ---- prompt bootstrap ------------------------------------------------

    def initial_directive_bn(self) -> str:
        return build_node_directive_bn(self.flow, self.current_node, self.order, self.merchant)

    def opening_question_bn(self) -> str:
        """The deterministic first question spoken right after the greeting."""
        return self.flow.opening_question_bn(self.order, self.merchant)

    def current_instruction_bn(self) -> str:
        return self.flow.spoken_instruction_bn(
            self.stage, self.slots, self.settings, self.order, self.merchant
        )

    # ---- the loop --------------------------------------------------------

    def save(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Store the slots the model extracted, re-derive the node, and return
        the tool result the model reads (ok/saved/instruction)."""
        known = self.flow.slot_properties()
        saved = {
            key: value
            for key, value in (fields or {}).items()
            if key in known and value is not None and value != ""
        }
        self.slots.update(saved)
        return self.advance(saved_keys=sorted(saved))

    def advance(self, saved_keys: list[str] | None = None) -> dict[str, Any]:
        self.stage = self.flow.next_missing_stage(self.slots, self.settings, self.order)
        node = self.flow.node_for_stage(self.stage)
        if node != self.current_node:
            directive = build_node_directive_bn(self.flow, node, self.order, self.merchant)
            if self.context is not None:
                self.context.add_message({"role": "system", "content": directive})
            logger.info(
                f"flow_node_transition order={self.order.id} "
                f"{self.current_node} -> {node} (stage={self.stage})"
            )
            self.current_node = node
        return {
            "ok": True,
            "saved": saved_keys or [],
            "instruction": self.current_instruction_bn(),
        }

    # ---- persistence -----------------------------------------------------

    def flow_data(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Everything the call learned, written to orders.flow_data."""
        data = dict(self.slots)
        if extra:
            data.update({k: v for k, v in extra.items() if v not in (None, "")})
        return data
