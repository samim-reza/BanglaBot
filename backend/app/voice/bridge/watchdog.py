"""Silence and time limits: the two-strike silence watchdog (ask "can you hear me?",
then settle as ``auto_dropped``) and the per-call duration cap."""

from __future__ import annotations

import asyncio
import time

import structlog

from app.flows.base import OUTCOME_AUTO_DROPPED, OUTCOME_UNCLEAR
from app.voice.languages import phrase

logger = structlog.get_logger(__name__)


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
            and now >= self._silence_counting_paused_until
        )

    async def _watchdog(self) -> None:
        while not self.closed:
            await asyncio.sleep(0.5)
            if self.closed:
                return
            now = time.monotonic()
            if now - self.started_at >= self.max_call_seconds and not self.closing:
                await self._close_with_outcome(OUTCOME_UNCLEAR, timeout=True)
                return
            if self.closing:
                # Never re-prompt after a goodbye; close if the hangup was lost.
                if self._idle(now) and now - self.last_voice_activity_at >= self._goodbye_hangup_delay_seconds + 5.0:
                    await self._safe_close()
                    return
                continue
            if not self._idle(now):
                continue
            silence_started_at = max(self.last_customer_audio_at, self._silence_counting_paused_until, self.last_voice_activity_at)
            if now - silence_started_at < self.silence_seconds:
                continue
            self._silence_strikes += 1
            if self._silence_strikes == 1:
                await logger.ainfo("caller_silent_reask", call_log_id=self.call_log_id, silent_seconds=round(now - silence_started_at, 1))
                self.speak(phrase("still_there", self.active_language))
                continue
            await logger.ainfo("caller_silent_dropping", call_log_id=self.call_log_id)
            await self._close_with_outcome(OUTCOME_AUTO_DROPPED)
            return

    async def _close_with_outcome(self, outcome: str, *, timeout: bool = False) -> None:
        self.closing = True
        line = await self.agent.settle(outcome)
        await self._emit_state()
        utterance = self.speak(line, allow_barge_in=False, close_after=True)
        if utterance is None:
            await self._safe_close()
