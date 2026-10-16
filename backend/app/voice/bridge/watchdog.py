"""Silence and time limits: the silence watchdog (re-ask "can you hear me?" + the last
question ``voice_silence_reprompts`` times, then say goodbye and settle as
``auto_dropped``), finishing a line a noise burst cut off, and the per-call duration
cap (a goodbye at the limit, a hard stop if even that hangs).

The silence clock only runs while the line is idle: not while the agent speaks or
thinks, not while a caller turn is pending or the caller is mid-utterance — it starts
when the agent's last line finished playing (or the agent last became idle).
"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.flows.base import OUTCOME_AUTO_DROPPED, OUTCOME_UNCLEAR
from app.voice.audio import split_sentences
from app.voice.languages import ack_lines, phrase

logger = structlog.get_logger(__name__)

WATCHDOG_TICK_SECONDS = 0.5
# Past the time limit by this much (the goodbye itself hung), the call is closed regardless.
HARD_STOP_GRACE_SECONDS = 45.0
# A barge-in followed by no words for this long was noise: the agent finishes its line.
FALSE_BARGE_IN_SECONDS = 2.0


class WatchdogMixin:
    """Silence / max-duration supervision. Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    def _pause_silence_counting(self, seconds: float) -> None:
        until = time.monotonic() + max(0.0, seconds)
        if until > self._silence_counting_paused_until:
            self._silence_counting_paused_until = until

    def _idle(self, now: float) -> bool:
        return (
            not self.assistant_speaking
            and self._speech_queue.empty()
            and not self._agent_turn_running()
            and not self._pending_user_turn_text
            and not self._carry_text
            and not self._caller_mid_utterance()
            and now >= self._silence_counting_paused_until
        )

    async def _watchdog(self) -> None:
        while not self.closed:
            await asyncio.sleep(WATCHDOG_TICK_SECONDS)
            if self.closed:
                return
            now = time.monotonic()
            elapsed = now - self.started_at
            if elapsed >= self.max_call_seconds + HARD_STOP_GRACE_SECONDS:
                await logger.awarning("call_hard_stop", call_log_id=self.call_log_id, seconds=int(elapsed))
                await self._safe_close()
                return
            if elapsed >= self.max_call_seconds and not self.closing:
                await logger.ainfo("call_time_limit", call_log_id=self.call_log_id, seconds=self.max_call_seconds)
                await self._close_with_outcome(OUTCOME_UNCLEAR, timeout=True)
                continue
            if self.closing:
                # Never re-prompt after a goodbye; close if the hangup was lost.
                if self._idle(now) and now - self.last_voice_activity_at >= self._goodbye_hangup_delay_seconds + 5.0:
                    await self._safe_close()
                    return
                continue
            if not self._idle(now):
                self._last_busy_at = now
                continue
            if self._resume_unheard(now):
                continue
            silence_started_at = max(self.last_customer_audio_at, self._silence_counting_paused_until, self.last_voice_activity_at, self._last_busy_at)
            if now - silence_started_at < self.silence_seconds:
                continue
            self._silence_strikes += 1
            if self._silence_strikes <= self.silence_reprompts:
                line = self._reprompt_line()
                await logger.ainfo("caller_silent_reask", call_log_id=self.call_log_id, strike=self._silence_strikes, silent_seconds=round(now - silence_started_at, 1))
                self.messages.append({"role": "assistant", "content": line})
                self.speak(line)
                continue
            await logger.ainfo("caller_silent_dropping", call_log_id=self.call_log_id, strikes=self._silence_strikes)
            await self._close_with_outcome(OUTCOME_AUTO_DROPPED)

    def _reprompt_line(self) -> str:
        """"Hello, can you hear me?" (then "Are you still there?") plus the unanswered question."""
        ask = phrase("still_there" if self._silence_strikes <= 1 else "still_there_again", self.active_language)
        question = self._last_question()
        return f"{ask} {question}" if question else ask

    def _last_question(self) -> str:
        """The last question of the agent's latest real line (re-prompts and fillers skipped)."""
        language = self.active_language
        fillers = set(ack_lines(language)) | {phrase("working", language)}
        asks = (phrase("still_there", language), phrase("still_there_again", language))
        for role, text in reversed(self.transcript_lines):
            if role != "Agent" or text in fillers or text.startswith(asks):
                continue
            questions = [sentence for sentence in split_sentences(text) if sentence.endswith("?")]
            return questions[-1] if questions else ""
        return ""

    def _resume_unheard(self, now: float) -> bool:
        """A barge-in that brought no words (a cough, a door, a TV): finish the line it cut off."""
        if not self._unheard or now - self._unheard_at < FALSE_BARGE_IN_SECONDS:
            return False
        pieces, self._unheard = list(self._unheard), []
        for utterance, _ in pieces:
            if utterance.message_ref is not None:
                utterance.message_ref["content"] = utterance.text
        text = " ".join(rest for _, rest in pieces)
        logger.info("false_barge_in_resumed", call_log_id=self.call_log_id, preview=text[:80])
        self.speak(text)
        return True

    async def _close_with_outcome(self, outcome: str, *, timeout: bool = False) -> None:
        self.closing = True
        try:
            line = await self.agent.settle(outcome)
        except Exception as exc:  # noqa: BLE001 — the goodbye is said and the call ends regardless
            await logger.awarning("bridge_settle_failed", call_log_id=self.call_log_id, outcome=outcome, error=str(exc))
            line = phrase("closing_dropped" if outcome == OUTCOME_AUTO_DROPPED else "closing_timeout", self.active_language)
        await self._emit_state()
        utterance = self.speak(line, allow_barge_in=False, close_after=True)
        if utterance is None:
            await self._safe_close()
