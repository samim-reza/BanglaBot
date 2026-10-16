"""After the booking: tell the caller a confirmation text is coming (when one will be sent)."""

from __future__ import annotations

from typing import Any

from app.flows.base import CommitAction
from app.flows.context import CallContext
from app.skills.base import BoundSkill, Skill
from app.skills.library.lines import L, line


class NotifySkill(Skill):
    key = "notify"
    kind = "effect"
    label = L("Confirmation text")
    description = L("Mentions the confirmation SMS (turn texts on in Notifications).")
    lines = (line("sms_note", "We'll text you the details.", label="Text coming", static=True),)

    def notes(self, b: BoundSkill, action: CommitAction, slots: dict[str, Any], ctx: CallContext, language: str) -> list[str]:
        from app.services.sms_service import planned_kind

        phone = str(action.fields.get("customer_phone") or ctx.record_value("customer_phone", "") or "")
        kind = str(action.fields.get("kind") or ctx.record_value("kind", "") or "")
        if not planned_kind(ctx.merchant, action.outcome, record_kind=kind, phone=phone):
            return []
        return [b.text("sms_note", language)]

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [b.text("sms_note", language)]


__all__ = ["NotifySkill"]
