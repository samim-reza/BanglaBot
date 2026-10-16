"""Caller turns: back-to-back ``completed`` STT events merged into one turn (a longer
window on steps that expect a long answer), then answered one at a time by the agent.

A caller who keeps talking is not answered mid-thought: a finished turn is held open
while the STT still hears words, and a reply the agent is still thinking out (nothing
said or saved yet) is dropped and its text merged with what follows. Every turn gets an
answer — a hold line when the reply is slow, the recovery line when it fails, gets
stuck past the deadline or says nothing.
"""

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
# The caller is mid-utterance while the STT reported speech / words this recently...
CALLER_ACTIVE_SECONDS = 1.5
# ...which holds a finished turn open, at most this long, for the rest of the sentence.
MAX_TURN_HOLD_SECONDS = 12.0
# A turn longer than this reaches the model as its beginning and end (~6 min of speech).
MAX_TURN_CHARS = 6000
# "Let me check that." when the reply takes this long...
HOLD_LINE_SECONDS = 4.0
# ...and a turn still running after this is abandoned (recovery line), never waited on forever.
TURN_DEADLINE_SECONDS = 30.0


def _join(*parts: str) -> str:
    return " ".join(" ".join(parts).split())


def clip_turn(text: str, limit: int | None = None) -> str:
    """Keep the beginning (who / what) and the end (the actual ask) of a very long turn."""
    limit = limit or MAX_TURN_CHARS
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head - 3
    return f"{text[:head].rsplit(' ', 1)[0]} … {text[-tail:].split(' ', 1)[-1]}"


class TurnsMixin:
    """Caller turn merging and agent-turn serialization. Mixed into
    :class:`~app.voice.bridge.core.CallBridge`."""

    def _merge_window(self) -> float:
        hint = self.flow.stage_hint(self.runtime.stage) or {}
        return LONG_TURN_MERGE_SECONDS if hint.get("long_answer") else TURN_MERGE_SECONDS

    def _caller_mid_utterance(self) -> bool:
        """The STT heard the caller start (or keep) talking since the last final, just now."""
        return self._caller_speech_open and time.monotonic() - self._caller_active_at < CALLER_ACTIVE_SECONDS

    def _on_caller_words(self, text: str) -> None:
        """Interim words: the caller is talking — keep the turn open, and drop a reply the
        agent is still thinking out so the whole thought is answered once."""
        text = " ".join(str(text or "").split())
        if not text or self.closing or hearing.is_backchannel(text) or self._phantom_transcript_reason(text):
            return
        now = time.monotonic()
        self._caller_speech_open = True
        self._caller_active_at = now
        self.last_customer_audio_at = now
        self._silence_strikes = 0
        self._unheard.clear()
        self._resume_caller_turn()

    def _queue_user_turn(self, text: str) -> None:
        self._pending_user_turn_text = _join(self._pending_user_turn_text, text)
        self._unheard.clear()
        self._resume_caller_turn()
        self._schedule_turn_flush()

    def _schedule_turn_flush(self) -> None:
        self._pending_user_turn_seq += 1
        seq = self._pending_user_turn_seq
        if self._pending_user_turn_task and not self._pending_user_turn_task.done():
            self._pending_user_turn_task.cancel()
        self._pending_user_turn_task = asyncio.create_task(self._flush_user_turn_after_delay(seq))

    def _resume_caller_turn(self) -> None:
        """The caller carried on while the agent was still thinking: cancel that reply (the
        agent rolls the turn back) and put its text in front of what the caller says next."""
        task = self._agent_turn_task
        if task is None or task.done() or not self._agent_turn_text or not getattr(self.agent, "interruptible", False):
            return
        # The turn itself first, synchronously: it must not get one more step past this check.
        if self._agent_handle_task is not None:
            self._agent_handle_task.cancel()
        task.cancel()
        self._agent_turn_task = None
        self._carry_text = _join(self._carry_text, self._agent_turn_text, self._turn_backlog)
        self._agent_turn_text = ""
        self._turn_backlog = ""
        logger.info("caller_kept_talking", call_log_id=self.call_log_id, carried_chars=len(self._carry_text))
        if not (self._pending_user_turn_task and not self._pending_user_turn_task.done()):
            self._schedule_turn_flush()

    async def _flush_user_turn_after_delay(self, seq: int) -> None:
        try:
            await asyncio.sleep(self._merge_window())
            held = 0.0
            # Still talking (speech since the last final): wait for the rest of the sentence.
            while self._caller_mid_utterance() and held < MAX_TURN_HOLD_SECONDS:
                await asyncio.sleep(0.1)
                held += 0.1
        except asyncio.CancelledError:
            return
        if seq != self._pending_user_turn_seq or self.closed:
            return
        text = " ".join(str(self._pending_user_turn_text or "").split())
        self._pending_user_turn_text = ""
        carried, self._carry_text = self._carry_text, ""
        if text:
            await self._record_user_transcript(text)
        if self.closed:
            return
        if not carried and (not text or (hearing.is_backchannel(text) and self._agent_turn_running())):
            return
        self._submit_turn(_join(carried, text), resumed=bool(carried))

    async def _record_user_transcript(self, text: str) -> None:
        self._silence_strikes = 0
        now = time.monotonic()
        self.last_customer_audio_at = now
        self.last_voice_activity_at = now
        self.transcript_lines.append(("Customer", text))
        await self._emit({"event": "transcript", "role": "caller", "text": text})

    def _submit_turn(self, text: str, *, resumed: bool = False) -> None:
        self._turn_backlog = _join(self._turn_backlog, text)
        if resumed:
            # Its instant ack was already spoken before the caller carried on.
            self.agent.skip_ack = True
        if self._agent_turn_task and not self._agent_turn_task.done():
            return
        self._agent_turn_task = asyncio.create_task(self._drain_turns())

    def _agent_turn_running(self) -> bool:
        return bool(self._agent_turn_task and not self._agent_turn_task.done())

    async def _drain_turns(self) -> None:
        while not self.closed and self._turn_backlog and not self.closing:
            text = self._turn_backlog
            self._turn_backlog = ""
            self._agent_turn_text = text
            self._turn_started_at = time.monotonic()
            self._turn_first_audio_logged = False
            self._refresh_prepared()
            replies = self._replies_queued
            try:
                await self._run_agent_turn(clip_turn(text), replies)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — the line must never go dead
                await logger.awarning("bridge_agent_turn_failed", call_log_id=self.call_log_id, error=str(exc), error_type=type(exc).__name__)
            self._agent_turn_text = ""
            if self._replies_queued == replies and not self.closed and not self.closing:
                # Failed, stuck or silent (a tool that stopped without a line): never leave the caller hanging.
                await logger.ainfo("agent_turn_unanswered", call_log_id=self.call_log_id)
                self.speak(phrase("recovery", self.active_language))
            await self._emit_state()
            await self._persist_transcript()

    async def _run_agent_turn(self, text: str, replies: int) -> None:
        """``handle_turn`` under supervision: a hold line when the reply is slow, cancelled at the deadline."""
        task = self._agent_handle_task = asyncio.create_task(self.agent.handle_turn(text))
        first = min(HOLD_LINE_SECONDS, TURN_DEADLINE_SECONDS)
        try:
            done, _ = await asyncio.wait({task}, timeout=first)
            quiet = self._replies_queued == replies and not self.assistant_speaking and self._speech_queue.empty()
            if not done and first < TURN_DEADLINE_SECONDS and quiet and not self.closing:
                self.speak(phrase("working", self.active_language))
            if not done:
                done, _ = await asyncio.wait({task}, timeout=TURN_DEADLINE_SECONDS - first)
        except asyncio.CancelledError:
            task.cancel()
            raise
        if not done:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise TimeoutError(f"agent turn still running after {TURN_DEADLINE_SECONDS:.0f} s")
        task.result()
