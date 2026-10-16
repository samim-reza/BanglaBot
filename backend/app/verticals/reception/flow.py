"""The reception pipeline flow: read the message back, write it as a ``message`` record, close."""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_LEAD, CommitAction
from app.flows.context import CallContext
from app.pipeline.blueprint import Branch
from app.pipeline.flow import PipelineFlow
from app.verticals.reception.contact import caller_phone
from app.verticals.reception.skills import caller_orders
from app.voice.languages import normalize_language


class ReceptionPipelineFlow(PipelineFlow):
    @property
    def lines(self):  # noqa: ANN201
        return self.cp.bound["confirm"]

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        """The caller's own orders (found by caller ID) — what the agent may tell them about."""
        return [*super().call_facts(ctx, language), *caller_orders(ctx)]

    def readback_core(self, slots: dict[str, Any], ctx: CallContext, language: str) -> tuple[str, str]:
        lang = normalize_language(language)
        message = str(slots.get("message", "")).strip().rstrip(".!?।")
        # The caller's own line needs no read-back; a number they gave does.
        if slots.get("phone") or not ctx.caller_number:
            phone = ctx.say_number(caller_phone(slots, ctx), lang)
            return self.lines.text("readback", lang, name=slots.get("caller_name", ""), message=message, phone=phone), ""
        return self.lines.text("readback_own_number", lang, name=slots.get("caller_name", ""), message=message), ""

    def commit_core(self, branch: Branch | None, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        return CommitAction(
            outcome=OUTCOME_LEAD,
            status="needs_review",
            fields={
                "kind": "message",
                "customer_name": slots.get("caller_name", ""),
                "customer_phone": caller_phone(slots, ctx),
                "items_summary": slots.get("message", ""),
                "details": {"message": slots.get("message", "")},
            },
        )

    def outcome_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return self.lines.text("closing_lead", language) if outcome == OUTCOME_LEAD else ""


__all__ = ["ReceptionPipelineFlow"]
