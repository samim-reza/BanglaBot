"""Call endings: outcome tools, transfers, end_call, silence/timeouts, and persisting outcomes."""

from __future__ import annotations

from typing import Any

import structlog

from app.flows import hearing
from app.flows.base import (
    MAX_REASKS,
    OUTCOME_AUTO_DROPPED,
    OUTCOME_EMERGENCY,
    OUTCOME_INQUIRY,
    OUTCOME_RELAY,
    OUTCOME_STATUS,
    OUTCOME_TRANSFER,
    OUTCOME_UNCLEAR,
    OUTCOME_WRONG_NUMBER,
    STAGE_RELAY,
    STAGE_WRONG_NUMBER,
    Terminal,
)
from app.flows.context import DIRECTION_INBOUND
from app.voice.languages import normalize_language, phrase
from app.voice.tools.store import ToolResult
from app.voice.tools.text import _join, _note

logger = structlog.get_logger(__name__)


class EndingsMixin:
    async def _terminal(self, terminal: Terminal, args: dict[str, Any], caller_text: str) -> ToolResult:
        if self.outcome:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        language = self.language
        if terminal.requires_identity and self.flow.identity_gate and (
            self.runtime.stage in (STAGE_RELAY, STAGE_WRONG_NUMBER) or self.runtime.slots.get("identity_confirmed") is not True
        ):
            # Only the named person decides; anyone else goes through end_call.
            instruction = self.runtime.current_instruction().for_model(language)
            return ToolResult(payload={"ok": False, "reason": "identity_not_confirmed", "instruction": instruction})
        if terminal.gate:
            if hearing.supports(caller_text, "later"):
                return await self._settle_later()
            if not hearing.supports(caller_text, terminal.gate):
                self.runtime.reasks += 1
                if self.runtime.reasks <= MAX_REASKS:
                    line = self.flow.reask_line(self.runtime.reasks, language)
                    return ToolResult(
                        payload={"ok": False, "reason": "answer_unclear", "reasked": self.runtime.reasks, "instruction": f"(said) {line}"},
                        say=line,
                        stop=True,
                    )
                return await self._settle_unclear()
        note = ""
        template = terminal.note_template.get(normalize_language(language)) or terminal.note_template.get("en") or ""
        if template:
            try:
                note = template.format(**{key: str(args.get(key) or "") for key in terminal.properties})
            except (KeyError, IndexError, ValueError):
                note = template
        self.runtime.mark_decided(terminal.outcome)
        await self._set_outcome(terminal.outcome, note)
        if terminal.outcome == OUTCOME_EMERGENCY:
            self.closing_spoken = True
            line = self.flow.closing_line(OUTCOME_EMERGENCY, self.runtime.slots, self.runtime.ctx, language)
            if self.support_phone:
                return ToolResult(
                    payload={"ok": True, "outcome": OUTCOME_EMERGENCY, "instruction": "Say nothing."},
                    say=_join(line, phrase("closing_transfer", language)),
                    transfer_to=self.support_phone,
                    stop=True,
                    outcome=OUTCOME_EMERGENCY,
                )
            return ToolResult(
                payload={"ok": True, "outcome": OUTCOME_EMERGENCY, "instruction": "Say nothing."},
                say=line,
                hang_up=True,
                stop=True,
                outcome=OUTCOME_EMERGENCY,
            )
        if not self.runtime.done:
            # Confirmed, but the merchant wants the address checked: the backend
            # asks it right away and the closing line waits for end_call.
            instruction = self.runtime.current_instruction()
            return ToolResult(
                payload={"ok": True, "outcome": terminal.outcome, "stage": self.runtime.stage, "instruction": instruction.for_model(language)},
                say=instruction.text if instruction.verbatim else "",
                stop=bool(instruction.verbatim),
                outcome=terminal.outcome,
            )
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": terminal.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(terminal.outcome, self.runtime.slots, self.runtime.ctx, language),
            hang_up=True,
            stop=True,
            outcome=terminal.outcome,
        )

    async def _settle_later(self) -> ToolResult:
        await self._set_outcome(OUTCOME_UNCLEAR, _note("later", self.language))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_UNCLEAR, "instruction": "Say nothing."},
            say=phrase("closing_callback", self.language),
            hang_up=True,
            stop=True,
            outcome=OUTCOME_UNCLEAR,
        )

    async def _settle_unclear(self, *, note: str = "") -> ToolResult:
        """Unclear after the re-asks (or a failed write): a person follows up.

        An inbound caller's partial details are kept as a lead when the flow can."""
        language = self.language
        kept = await self._keep_fallback(note=note or _note(OUTCOME_UNCLEAR, language))
        if not kept:
            await self._set_outcome(OUTCOME_UNCLEAR, note or _note(OUTCOME_UNCLEAR, language))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(OUTCOME_UNCLEAR, self.runtime.slots, self.runtime.ctx, language),
            hang_up=True,
            stop=True,
            outcome=self.outcome,
        )

    async def _keep_fallback(self, *, note: str = "") -> bool:
        """Write the flow's fallback (e.g. a partial lead) for an inbound call that ends early."""
        if self.outcome or self.flow.direction != DIRECTION_INBOUND:
            return False
        action = self.flow.fallback_action(self.runtime.slots, self.runtime.ctx)
        if action is None:
            return False
        if note and not action.note:
            action.note = note
        try:
            result = await self.store.commit(
                action, final_node=self.runtime.current_node, flow_data=self.runtime.flow_data(), language=self.language
            )
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("fallback_commit_failed", flow=self.flow.key, error=str(exc))
            return False
        if not result.ok:
            return False
        self.record_id = result.record_id or self.record_id
        self.outcome = action.outcome
        self.runtime.outcome = action.outcome
        return True

    async def _transfer(self, args: dict[str, Any]) -> ToolResult:
        language = self.language
        if self.outcome:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        note = _note(OUTCOME_TRANSFER, language)
        reason = str(args.get("reason") or "").strip()
        if reason:
            note = f"{note} ({reason})"
        kept = await self._keep_fallback(note=note)
        if not kept:
            await self._set_outcome(OUTCOME_TRANSFER, note)
        self.closing_spoken = True
        if self.support_phone:
            return ToolResult(
                payload={"ok": True, "outcome": OUTCOME_TRANSFER, "instruction": "Say nothing."},
                say=phrase("closing_transfer", language),
                transfer_to=self.support_phone,
                stop=True,
                outcome=OUTCOME_TRANSFER,
            )
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_TRANSFER, "instruction": "Say nothing."},
            say=phrase("closing_transfer_callback", language),
            hang_up=True,
            stop=True,
            outcome=OUTCOME_TRANSFER,
        )

    async def _end_call(self, args: dict[str, Any], caller_text: str) -> ToolResult:
        language = self.language
        if self.outcome:
            if not self.closing_spoken:
                # Outcome recorded before the address step; say goodbye now.
                return await self.closing_result()
            # A terminal already spoke its closing; the agent is hanging up.
            return ToolResult(payload={"ok": True, "outcome": self.outcome}, hang_up=True, stop=True, outcome=self.outcome)
        stage = self.runtime.stage
        ctx = self.runtime.ctx
        reason = str(args.get("reason") or "").strip()
        if stage == STAGE_RELAY:
            outcome, say, note = OUTCOME_RELAY, self.flow.closing_line(OUTCOME_RELAY, self.runtime.slots, ctx, language), _note(OUTCOME_RELAY, language)
        elif stage == STAGE_WRONG_NUMBER:
            outcome, say, note = (
                OUTCOME_WRONG_NUMBER,
                self.flow.closing_line(OUTCOME_WRONG_NUMBER, self.runtime.slots, ctx, language),
                _note(OUTCOME_WRONG_NUMBER, language),
            )
        elif hearing.supports(caller_text, "later") or "later" in reason.lower():
            if await self._keep_fallback(note=_note("later", language)):
                self.closing_spoken = True
                return ToolResult(
                    payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
                    say=self.flow.closing_line(self.outcome, self.runtime.slots, ctx, language),
                    hang_up=True,
                    stop=True,
                    outcome=self.outcome,
                )
            outcome, say, note = OUTCOME_UNCLEAR, phrase("closing_callback", language), _note("later", language)
        elif self.flow.direction == DIRECTION_INBOUND:
            if await self._keep_fallback():
                self.closing_spoken = True
                return ToolResult(
                    payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
                    say=self.flow.closing_line(self.outcome, self.runtime.slots, ctx, language),
                    hang_up=True,
                    stop=True,
                    outcome=self.outcome,
                )
            # A caller who only asked questions: nothing to follow up.
            outcome, say, note = OUTCOME_INQUIRY, phrase("closing_inquiry", language), ""
        else:
            outcome, say = OUTCOME_UNCLEAR, self.flow.closing_line(OUTCOME_UNCLEAR, self.runtime.slots, ctx, language)
            note = _note(OUTCOME_UNCLEAR, language)
            if reason:
                note = f"{note} ({reason})"
        await self._set_outcome(outcome, note)
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": outcome, "instruction": "Say nothing."},
            say=say,
            hang_up=True,
            stop=True,
            outcome=outcome,
        )

    async def abandon(self, outcome: str, *, note: str = "") -> None:
        """Record an outcome for a call nobody we should talk to answered (divert / voicemail)."""
        if not self.outcome:
            await self._set_outcome(outcome, note or _note(outcome, self.language))

    async def settle(self, outcome: str, *, note: str = "") -> str:
        """Commit an agent-decided outcome (auto-dropped, timeout). Returns the closing line."""
        language = self.language
        if not self.outcome:
            if not await self._keep_fallback(note=note or _note(outcome, language)):
                await self._set_outcome(outcome, note or _note(outcome, language))
        if outcome == OUTCOME_AUTO_DROPPED:
            return phrase("closing_dropped", language)
        return phrase("closing_timeout", language)

    async def finish_inbound(self) -> None:
        """An inbound call ended without an outcome (the caller hung up)."""
        if self.outcome:
            return
        if not await self._keep_fallback():
            await self._set_outcome(OUTCOME_INQUIRY, "")

    async def _set_outcome(self, outcome: str, note: str) -> None:
        self.outcome = outcome
        self.runtime.outcome = outcome
        if note:
            self.note_lines.append(note)
        try:
            await self.store.set_outcome(
                outcome=outcome,
                status=OUTCOME_STATUS.get(outcome, "needs_review"),
                final_node=self.runtime.current_node,
                flow_data=self.runtime.flow_data(),
                note=note,
                language=self.language,
            )
        except Exception as exc:  # noqa: BLE001 — the line must never go dead over a DB hiccup
            await logger.awarning("call_outcome_persist_failed", outcome=outcome, error=str(exc))

