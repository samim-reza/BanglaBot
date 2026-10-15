"""Turns answered without the model: a clean yes/no on a scripted step (keyword hearing,
or Jev for a natural answer) and general questions another caller already asked
(the FAQ cache)."""

from __future__ import annotations

from typing import Any

import structlog

from app.flows import hearing
from app.flows.base import STAGE_COMMIT, STAGE_DONE, STAGE_RELAY, STAGE_WRONG_NUMBER
from app.pipeline import faq_cache
from app.voice import jev
from app.voice.tools import SAVE_DETAILS, ToolResult

logger = structlog.get_logger(__name__)


class FastPathMixin:
    """Mixed into :class:`~app.voice.agent.core.CallAgent`."""

    async def _cached_answer(self, text: str) -> bool:
        """A general question another caller already asked: reuse the answer, then re-ask the current step."""
        answer = await faq_cache.lookup(self.ctx, self.runtime.stage, self.language, text)
        if not answer:
            return False
        instruction = self.runtime.current_instruction()
        line = f"{answer} {instruction.text}" if instruction.verbatim and not instruction.end_call else answer
        self._record_turn(text, ToolResult(payload={}, say=line))
        logger.info("turn_faq_cache_hit", call_log_id=self.call_log_id, stage=self.runtime.stage)
        return True

    async def _fast_path(self, text: str) -> bool:
        """Answer scripted yes/no steps without the model.

        Steps with a backend-owned next line (identity, address check, a booking
        read-back, "will you come?") are answered from the hearing module when the
        caller's words are unambiguous: the slot is saved and the next line is
        spoken straight away — from the TTS cache when it is a fixed line. Anything
        less than a clean answer goes the normal way.
        """
        if self.speaker.closing:
            return False
        stage = self.runtime.stage
        labels = hearing.classify(text)
        if not labels:
            # Nothing the keyword matcher recognises: maybe a natural yes/no Jev can settle.
            fields = await self._jev_fields(stage, text)
            return bool(fields) and await self._speak_fast_fields(stage, text, fields, heard=self._jev_heard(fields))
        if "repeat" in labels:
            return False
        terminal = getattr(self.flow, "fast_terminal", None)
        if terminal is not None:
            name = terminal(stage, text, labels, self.runtime.slots, self.ctx)
            if name:
                result = await self.tools.execute(name, {}, caller_text=text)
                if result.say:
                    self._record_turn(text, result)
                    logger.info("turn_fast_path", call_log_id=self.call_log_id, stage=stage, terminal=name)
                    return True
                return False
        if "later" in labels or hearing.looks_like_question(text):
            return False
        fields = self.flow.fast_fields(stage, text, labels, self.runtime.slots, self.ctx)
        heard = text
        if not fields:
            fields = await self._jev_fields(stage, text, labels)
            heard = self._jev_heard(fields)
        if not fields:
            return False
        return await self._speak_fast_fields(stage, text, fields, heard=heard)

    async def _jev_fields(self, stage: str, text: str, labels: set[str] | None = None) -> dict[str, Any] | None:
        """A yes/no step the keyword matcher couldn't settle: ask Jev (off without an API key)."""
        slot = (getattr(self.flow, "yes_no_stages", None) or {}).get(stage)
        if not slot or not jev.enabled(self.language) or hearing.looks_like_question(text):
            return None
        if labels and labels & {"repeat", "later", "not_me", "wrong_number"}:
            return None
        confirms_cancel = getattr(self.flow, "confirms_cancellation", None)
        if confirms_cancel is not None and confirms_cancel(self.runtime.slots, self.ctx):
            # A cancellation needs the caller's own unmistakable words — never a model's guess.
            return None
        question = next((m.get("content") or "" for m in reversed(self.messages) if m.get("role") == "assistant"), "")
        decision = await jev.decide_yes_no(str(question), text, language=self.language)
        if decision is None:
            return None
        return {slot: decision == "yes"}

    @staticmethod
    def _jev_heard(fields: dict[str, Any] | None) -> str:
        """What the hearing gate checks when Jev decided: its confident verdict, as a plain answer."""
        if not fields:
            return ""
        return "yes" if next(iter(fields.values())) is True else "no"

    async def _speak_fast_fields(self, stage: str, text: str, fields: dict[str, Any], *, heard: str = "") -> bool:
        # Decide whether a line would be spoken BEFORE touching the runtime, so a
        # step the model must phrase itself leaves the flow untouched.
        preview = self.runtime.preview(fields)
        speakable = (
            (preview.instruction.verbatim and not preview.instruction.end_call)
            or preview.stage in (STAGE_COMMIT, STAGE_RELAY, STAGE_WRONG_NUMBER)
            or (preview.stage == STAGE_DONE and bool(self.tools.outcome) and not self.tools.closing_spoken)
        )
        if not speakable:
            return False
        result = await self.tools.execute(SAVE_DETAILS, fields, caller_text=heard or text)
        if not result.say:
            return False
        self._record_turn(text, result)
        logger.info("turn_fast_path", call_log_id=self.call_log_id, stage=stage, next_stage=self.runtime.stage, saved=sorted(fields))
        return True
