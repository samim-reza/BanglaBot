"""Audio out: the speech queue, TTS synthesis (two units in flight), 20 ms playout
paced ~0.6 s ahead of real time, playback marks, and interruption on barge-in."""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

import structlog

from app.voice.providers.overrides import provider_override
from app.voice.audio import (
    FRAME_BYTES,
    FRAME_SECONDS,
    clean_spoken_text,
    goodbye_hangup_delay_seconds,
    sentence_units,
    speech_units,
    trim_ulaw_silence,
)
from app.voice.bridge.utterance import _Utterance
from app.voice.languages import ack_lines
from app.voice.providers.tts import get_tts_for
from app.voice.tts import TTSError

logger = structlog.get_logger(__name__)

# How far ahead of real time outbound audio may run.
PLAYOUT_LEAD_SECONDS = 0.6


class SpeakerMixin:
    """The agent's voice (Speaker protocol). Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    def speak(
        self,
        text: str,
        *,
        allow_barge_in: bool = True,
        message_ref: dict[str, Any] | None = None,
        close_after: bool = False,
        transfer_to: str = "",
    ) -> _Utterance | None:
        """Queue a line for the caller. Returns the utterance (``done`` fires after playback)."""
        text = clean_spoken_text(text)
        if not text or self.closed:
            return None
        if close_after or transfer_to:
            allow_barge_in = False
            self._goodbye_hangup_delay_seconds = goodbye_hangup_delay_seconds(text)
        utterance = _Utterance(text=text, allow_barge_in=allow_barge_in, message_ref=message_ref, close_after=close_after, transfer_to=transfer_to)
        self._pause_silence_counting(3.0)
        self._speech_queue.put_nowait(utterance)
        return utterance

    def schedule_hangup(self) -> None:
        self._schedule_hangup(None)

    async def _warm_tts_cache(self) -> None:
        try:
            for language in self.supported_languages:
                tts = get_tts_for(language, provider_override(self.merchant, "tts_chain"))
                lines = list(self.flow.prefetch_lines(self.ctx, language)) + list(ack_lines(language))
                count = await tts.warm(sentence_units(lines), language=language, persona=self.persona, voice=self.voice)
                if count:
                    await logger.ainfo("tts_cache_warmed", call_log_id=self.call_log_id, language=language, synthesized=count)
        except Exception as exc:  # noqa: BLE001 — warming is an optimization only
            await logger.awarning("tts_cache_warm_failed", call_log_id=self.call_log_id, error=str(exc))

    async def _speaker_loop(self) -> None:
        while not self.closed:
            utterance = await self._speech_queue.get()
            if self.closed:
                utterance.done.set()
                return
            if utterance.interrupted:
                utterance.done.set()
                continue
            try:
                await self._play_utterance(utterance)
            except asyncio.CancelledError:
                utterance.done.set()
                raise
            except Exception as exc:  # noqa: BLE001 — keep speaking the next line
                await logger.awarning("bridge_playback_failed", call_log_id=self.call_log_id, error=str(exc))
                utterance.done.set()

    def _count_tts(self, provider: str, text: str, source: str) -> None:
        """Per-provider characters for this call — only ``synth`` costs money; cache tiers are savings."""
        row = self._tts_usage.setdefault(provider or "unknown", {"chars": 0, "cached_chars": 0})
        if source == "synth":
            row["chars"] += len(text)
            self.tts_chars += len(text)
        else:
            row["cached_chars"] += len(text)
            self.tts_cache_hits += 1

    async def _synthesize(self, text: str, language: str) -> bytes:
        async with self._tts_semaphore:
            try:
                tts = get_tts_for(language, provider_override(self.merchant, "tts_chain"))
            except TTSError as exc:
                await logger.awarning("bridge_tts_failed", call_log_id=self.call_log_id, error=str(exc), preview=text[:80])
                return b""
            try:
                synthesize_ex = getattr(tts, "synthesize_ex", None)
                if synthesize_ex is None:
                    self.tts_chars += len(text)
                    return await tts.synthesize(text, language=language, persona=self.persona, voice=self.voice)
                audio, provider, source = await synthesize_ex(text, language=language, persona=self.persona, voice=self.voice)
                self._count_tts(provider, text, source)
                return audio
            except TTSError as exc:
                await logger.awarning("bridge_tts_failed", call_log_id=self.call_log_id, error=str(exc), preview=text[:80])
                return b""

    async def _play_utterance(self, utterance: _Utterance) -> None:
        sentences = speech_units(utterance.text)
        language = self.active_language
        synth_tasks = [asyncio.create_task(self._synthesize(sentence, language)) for sentence in sentences]
        self._current_utterance = utterance
        self.assistant_speaking = True
        self._barge_in_allowed = utterance.allow_barge_in
        self._assistant_turn_started_at = time.monotonic()
        self._barge_in_window.clear()
        self._barge_in_prebuffer.clear()
        self._barge_in_loud_frames = 0
        self._recent_agent_lines.append((utterance.text, time.monotonic()))
        spoken: list[str] = []
        played_any = False
        try:
            for index, task in enumerate(synth_tasks):
                if utterance.interrupted or self.closed:
                    break
                audio = trim_ulaw_silence(await task)
                if not audio:
                    continue
                played_any = True
                fraction = await self._stream_audio(audio, utterance)
                if fraction >= 0.5:
                    spoken.append(sentences[index])
                if fraction < 1.0:
                    break
            if played_any and not utterance.interrupted and not self.closed:
                await self._await_playback_mark()
        finally:
            for task in synth_tasks:
                if not task.done():
                    task.cancel()
            self.assistant_speaking = False
            self._barge_in_allowed = True
            self._current_utterance = None
            self.last_voice_activity_at = time.monotonic()
            self._pause_silence_counting(1.0)
            utterance.spoken_text = " ".join(spoken)
            if utterance.interrupted and utterance.message_ref is not None:
                utterance.message_ref["content"] = utterance.spoken_text or "(interrupted before speaking)"
            if utterance.spoken_text:
                self._record_assistant_transcript(utterance.spoken_text)
            if utterance.transfer_to and not self.closed:
                asyncio.create_task(self._transfer_call(utterance.transfer_to))
            elif utterance.close_after and not self.closed:
                self._schedule_hangup(utterance)
            utterance.done.set()

    async def _stream_audio(self, audio: bytes, utterance: _Utterance) -> float:
        """Send μ-law to the caller in paced 20 ms frames. Returns the fraction sent."""
        if not self.stream_sid:
            return 0.0
        frames = [audio[i : i + FRAME_BYTES] for i in range(0, len(audio), FRAME_BYTES)]
        if not frames:
            return 1.0
        clock = max(time.monotonic(), self._playout_end)
        if not self._turn_first_audio_logged and self._turn_started_at:
            self._turn_first_audio_logged = True
            logger.info(
                "turn_first_audio",
                call_log_id=self.call_log_id,
                ms=int((time.monotonic() - self._turn_started_at) * 1000),
                preview=utterance.text[:60],
            )
        for index, frame in enumerate(frames):
            if utterance.interrupted or self.closed:
                return index / len(frames)
            await self.websocket.send_json(self._frame("media", media={"payload": base64.b64encode(frame).decode("ascii")}))
            clock += FRAME_SECONDS
            self._playout_end = clock
            self._silence_counting_paused_until = max(self._silence_counting_paused_until, clock + 1.0)
            ahead = clock - time.monotonic()
            if ahead > PLAYOUT_LEAD_SECONDS:
                await asyncio.sleep(ahead - PLAYOUT_LEAD_SECONDS)
        return 1.0

    async def _await_playback_mark(self) -> None:
        if not self.stream_sid or self.closed:
            return
        self._mark_counter += 1
        mark_name = f"agent-{self._mark_counter}"
        self._pending_playback_mark = mark_name
        self._playback_mark_event.clear()
        await self.websocket.send_json(self._frame("mark", mark={"name": mark_name}))
        timeout = max(0.5, self._playout_end - time.monotonic()) + 3.0
        try:
            await asyncio.wait_for(self._playback_mark_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if self._pending_playback_mark == mark_name:
                self._pending_playback_mark = None
                await logger.awarning("playback_mark_timeout", call_log_id=self.call_log_id, mark_name=mark_name)

    async def _interrupt_playback(self, reason: str) -> None:
        current = self._current_utterance
        if current is not None and not current.interrupted:
            current.interrupted = True
            if self.stream_sid and not self.closed:
                try:
                    await self.websocket.send_json(self._frame("clear"))
                except Exception:  # noqa: BLE001
                    pass
            self._playout_end = time.monotonic()
            self.assistant_speaking = False
            await logger.ainfo("agent_interrupted", call_log_id=self.call_log_id, reason=reason, preview=current.text[:80])
        kept: list[_Utterance] = []
        while not self._speech_queue.empty():
            queued = self._speech_queue.get_nowait()
            if queued.allow_barge_in:
                queued.interrupted = True
                queued.done.set()
            else:
                kept.append(queued)
        for queued in kept:
            self._speech_queue.put_nowait(queued)
