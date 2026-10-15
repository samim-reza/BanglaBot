"""Caller turns: back-to-back ``completed`` STT events merged into one turn (a longer
window on steps that expect a long answer), then answered one at a time by the agent."""

from __future__ import annotations

import asyncio
import time

import structlog

from app.flows import hearing
from app.voice.languages import phrase

logger = structlog.get_logger(__name__)

# Back-to-back ``completed`` STT events inside this window are one caller turn.
TURN_MERGE_SECONDS = 0.4
# ...and on steps that expect a long answer (address, phone number, problem).
LONG_TURN_MERGE_SECONDS = 1.1


class TurnsMixin:
    """Caller turn merging and agent-turn serialization. Mixed into
    :class:`~app.voice.bridge.core.CallBridge`."""

    def _merge_window(self) -> float:
        hint = self.flow.stage_hint(self.runtime.stage) or {}
        return LONG_TURN_MERGE_SECONDS if hint.get("long_answer") else TURN_MERGE_SECONDS

    def _queue_user_turn(self, text: str) -> None:
        self._pending_user_turn_text = " ".join(f"{self._pending_user_turn_text} {text}".split())
        self._pending_user_turn_seq += 1
        seq = self._pending_user_turn_seq
        if self._pending_user_turn_task and not self._pending_user_turn_task.done():
            self._pending_user_turn_task.cancel()
        self._pending_user_turn_task = asyncio.create_task(self._flush_user_turn_after_delay(seq))

    async def _flush_user_turn_after_delay(self, seq: int) -> None:
        try:
            await asyncio.sleep(self._merge_window())
        except asyncio.CancelledError:
            return
        if seq != self._pending_user_turn_seq or self.closed:
            return
        text = " ".join(str(self._pending_user_turn_text or "").split())
        self._pending_user_turn_text = ""
        if not text:
            return
        await self._record_user_transcript(text)
        if self.closed:
            return
        if hearing.is_backchannel(text) and self._agent_turn_running():
            return
        self._submit_turn(text)

    async def _record_user_transcript(self, text: str) -> None:
        self._silence_strikes = 0
        now = time.monotonic()
        self.last_customer_audio_at = now
        self.last_voice_activity_at = now
        self.transcript_lines.append(("Customer", text))
        await self._emit({"event": "transcript", "role": "caller", "text": text})

    def _submit_turn(self, text: str) -> None:
        self._turn_backlog = " ".join(f"{self._turn_backlog} {text}".split())
        if self._agent_turn_task and not self._agent_turn_task.done():
            return
        self._agent_turn_task = asyncio.create_task(self._drain_turns())

    def _agent_turn_running(self) -> bool:
        return bool(self._agent_turn_task and not self._agent_turn_task.done())

    async def _drain_turns(self) -> None:
        while not self.closed and self._turn_backlog and not self.closing:
            text = self._turn_backlog
            self._turn_backlog = ""
            self._turn_started_at = time.monotonic()
            self._turn_first_audio_logged = False
            self._refresh_prepared()
            try:
                await self.agent.handle_turn(text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — the line must never go dead
                await logger.awarning("bridge_agent_turn_failed", call_log_id=self.call_log_id, error=str(exc), error_type=type(exc).__name__)
                if not self.closed and not self.closing:
                    self.speak(phrase("recovery", self.active_language))
            await self._emit_state()
            await self._persist_transcript()
