"""Writing the result once everything is collected and confirmed, and the closing line."""

from __future__ import annotations


import structlog

from app.flows.base import CommitAction, CommitResult
from app.voice.languages import phrase
from app.voice.tools.store import ToolResult
from app.voice.tools.text import _note

logger = structlog.get_logger(__name__)


class CommitMixin:
    async def _commit(self, reply: str = "") -> ToolResult:
        language = self.language
        ctx = self.runtime.ctx
        action = self.flow.commit_action(self.runtime.slots, ctx)
        if action is None:
            await logger.awarning("commit_action_missing", flow=self.flow.key, slots=sorted(self.runtime.slots))
            return await self._settle_unclear(note=_note("commit_failed", language))
        try:
            result = await self.store.commit(
                action,
                final_node=self.runtime.current_node,
                flow_data=self.runtime.flow_data(),
                language=language,
            )
        except Exception as exc:  # noqa: BLE001 — the line must never go dead over a DB hiccup
            await logger.awarning("commit_failed", flow=self.flow.key, error=str(exc))
            result = CommitResult(ok=False, reason="error")
        if result.ok:
            if result.record_id:
                self.record_id = result.record_id
            self.outcome = action.outcome
            self.runtime.mark_decided(action.outcome)
            if action.note:
                self.note_lines.append(action.note)
            self.closing_spoken = True
            closing_for = getattr(self.flow, "closing_for", None)
            if closing_for is not None:
                # Pipeline flows assemble outcome line + skill notes (text coming, pay link) + goodbye.
                say = closing_for(action, self.runtime.slots, ctx, language)
            else:
                say = self._with_sms_note(self.flow.closing_line(action.outcome, self.runtime.slots, ctx, language), action)
            await logger.ainfo("flow_committed", flow=self.flow.key, outcome=action.outcome, record_id=result.record_id)
            return ToolResult(
                payload={"ok": True, "outcome": action.outcome, "instruction": "Say nothing."},
                say=say,
                hang_up=True,
                stop=True,
                outcome=action.outcome,
            )
        await logger.ainfo("flow_commit_refused", flow=self.flow.key, reason=result.reason)
        if result.reason != "slot_taken":
            return await self._settle_unclear(note=_note("commit_failed", language))
        override = self.flow.on_commit_failed(result, self.runtime.slots, ctx)
        payload = self.runtime.advance(override=override)
        instruction = self.runtime.last_instruction
        if instruction is not None and instruction.verbatim:
            return self._speak_next(payload, instruction.text, stage=self.runtime.stage)
        return ToolResult(payload=payload)

    def _with_sms_note(self, say: str, action: CommitAction) -> str:
        """Tell the caller a text is coming, just before the goodbye."""
        from app.services.sms_service import planned_kind

        ctx = self.runtime.ctx
        phone = str(action.fields.get("customer_phone") or ctx.record_value("customer_phone", "") or "")
        kind = str(action.fields.get("kind") or ctx.record_value("kind", "") or "")
        if not planned_kind(ctx.merchant, action.outcome, record_kind=kind, phone=phone):
            return say
        note = phrase("sms_follows", self.language)
        for marker in (" Thank you", " ধন্যবাদ"):
            index = say.rfind(marker)
            if index > 0:
                return f"{say[:index]} {note}{say[index:]}"
        return f"{say} {note}"

    async def closing_result(self) -> ToolResult:
        """The closing line for an outcome that was recorded earlier (address step done).

        Re-persists the outcome so what the address step collected (address_correct,
        new_address) reaches the record's flow_data."""
        language = self.language
        self.closing_spoken = True
        await self._set_outcome(self.outcome, "")
        return ToolResult(
            payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(self.outcome, self.runtime.slots, self.runtime.ctx, language),
            hang_up=True,
            stop=True,
            outcome=self.outcome,
        )

