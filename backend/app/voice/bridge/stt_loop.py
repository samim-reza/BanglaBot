"""Speech-to-text: connecting and reconnecting the STT session, its events, and the
filters that drop phantom transcripts (prompt echo, the agent's own line, noise).

A dropped or broken STT socket is reconnected (the chain walk lands on the next
healthy provider); the caller's audio in the gap is buffered by the media loop. Only
after ``STT_MAX_RECONNECTS`` failures in a row does the call end — with a goodbye.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Any

import structlog

from app.flows.base import OUTCOME_AUTO_DROPPED
from app.voice.providers.overrides import provider_override
from app.flows import hearing
from app.voice.providers.base import STTSession
from app.voice.providers.stt import open_stt
from app.voice.stt import STTEvent

logger = structlog.get_logger(__name__)

# Reconnect attempts in a row before the call is ended (with the "can't hear you" goodbye)...
STT_MAX_RECONNECTS = 3
# ...a session that served the call this long was healthy, so a later drop starts the count over...
STT_HEALTHY_SECONDS = 20.0
# ...and the pause after a failed attempt (× the attempt number).
STT_RETRY_SECONDS = 0.5
# A transcript this long is real speech unless one word pair dominates it (see _long_real_speech).
LONG_TRANSCRIPT_TOKENS = 16
# A short agent line (an ack) heard back this soon is its echo, not the caller.
SHORT_ECHO_SECONDS = 4.0


def _long_real_speech(text: str) -> bool:
    """hearing's loop check is tuned for short Whisper hallucinations ("thank you thank you
    …"); a long real sentence repeats "and then" / "I was" a few times and must not be
    dropped as noise. Long text only counts as a loop when repetition dominates it."""
    toks = hearing.tokens(text)
    if len(toks) < LONG_TRANSCRIPT_TOKENS or any(marker in hearing.normalize(text) for marker in hearing.NOISE_PHRASES):
        return False
    top_pair = Counter(zip(toks, toks[1:])).most_common(1)[0][1]
    top_word = Counter(toks).most_common(1)[0][1]
    return top_pair * 4 < len(toks) and top_word * 2 < len(toks)


class SttMixin:
    """The caller's ears. Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    async def _open_stt(self) -> STTSession:
        """A connected session from the first healthy provider of the language's chain."""
        return await open_stt(
            language=self._transcription_language or self.primary_language,
            prompt=self._stt_prompt(),
            keyterms=self._stt_keyterms(),
            chain=provider_override(self.merchant, "stt_chain"),
        )

    async def _connect_stt(self) -> None:
        try:
            self._stt = await self._open_stt()
        except Exception as exc:  # noqa: BLE001 — the STT loop keeps trying (and says goodbye if it can't)
            await logger.awarning("bridge_stt_connect_failed", call_log_id=self.call_log_id, error=str(exc)[:200])

    async def _close_stt(self, stt: Any) -> None:
        if stt is None:
            return
        try:
            await stt.close()
        except Exception as exc:  # noqa: BLE001 — a session that won't close cleanly is gone anyway
            await logger.ainfo("bridge_stt_close_failed", call_log_id=self.call_log_id, error=str(exc)[:160])

    def _retire_stt(self, stt: Any) -> None:
        """Keep a finished session's billable usage for the call summary."""
        usage = getattr(stt, "usage", None)
        if callable(usage):
            try:
                self._stt_usage.append(usage())
            except Exception:  # noqa: BLE001 — metering only
                pass

    def _stt_keyterms(self) -> list[str]:
        """This call's proper nouns (business, doctors, products) for keyterm boosting."""
        terms: list[str] = []
        for hint in self.flow.transcription_hints(self.ctx):
            value = " ".join(str(hint or "").split())[:60]
            if value and value not in terms:
                terms.append(value)
        return terms

    def _stt_prompt(self) -> str:
        """The generic answer vocabulary plus THIS call's proper nouns.

        Names the transcriber has seen in the prompt come back spelled the way
        the business wrote them (doctor names, areas, products). The prompt-echo
        guard keeps using the generic part only, so a caller who actually says a
        name is never mistaken for the transcriber echoing its hint.
        """
        parts = [self._transcription_prompt]
        for hint in self.flow.transcription_hints(self.ctx):
            value = " ".join(str(hint or "").split())[:120]
            if value and value not in parts:
                parts.append(f"{value}.")
        return " ".join(parts)[:900].strip()

    async def _stt_loop(self) -> None:
        failures = 0
        while not self.closed:
            stt = self._stt
            if stt is not None:
                started = time.monotonic()
                try:
                    async for event in stt.events():
                        if self.closed:
                            return
                        if event.type == "closed":
                            break
                        try:
                            await self._on_stt_event(event)
                        except Exception as exc:  # noqa: BLE001 — one bad event must not deafen the call
                            await logger.awarning("bridge_stt_event_failed", call_log_id=self.call_log_id, error=str(exc))
                except Exception as exc:  # noqa: BLE001 — a broken stream is a drop, not the end of the call
                    await logger.awarning("bridge_stt_stream_failed", call_log_id=self.call_log_id, error=str(exc)[:160])
                if self.closed:
                    return
                if time.monotonic() - started >= STT_HEALTHY_SECONDS:
                    failures = 0
            failures += 1
            if failures > STT_MAX_RECONNECTS:
                await logger.awarning("bridge_stt_gave_up", call_log_id=self.call_log_id)
                await self._give_up_hearing()
                return
            await logger.awarning("bridge_stt_reconnecting", call_log_id=self.call_log_id, attempt=failures, provider=getattr(stt, "name", ""))
            if stt is not None:
                # Unset first: the media loop buffers the caller's audio until the next session is up.
                self._stt = None
                await self._close_stt(stt)
                self._retire_stt(stt)
            try:
                # The chain walk tries a provider that just failed (paused) last, so a dead
                # provider hands the call to the next one instead of retrying itself.
                self._stt = await self._open_stt()
                self._stt_send_failed = False
            except Exception as exc:  # noqa: BLE001
                await logger.awarning("bridge_stt_reconnect_failed", call_log_id=self.call_log_id, error=str(exc))
                await asyncio.sleep(STT_RETRY_SECONDS * failures)

    async def _give_up_hearing(self) -> None:
        """No transcriber can serve the call: say so and hang up (the record stays callable)."""
        if self.closing:
            await self._safe_close()
            return
        await self._interrupt_playback("stt_unavailable")
        await self._close_with_outcome(OUTCOME_AUTO_DROPPED)

    async def _on_stt_event(self, event: STTEvent) -> None:
        if event.type == "speech_started":
            # Restarts the silence clock and holds a finished turn open; only words reset the strikes.
            now = time.monotonic()
            self.last_customer_audio_at = now
            self._caller_speech_open = True
            self._caller_active_at = now
            if self.assistant_speaking and self._barge_in_allowed and self._barge_in_loud_frames >= self.settings.voice_barge_in_min_frames:
                await self._on_barge_in()
            return
        if event.type == "speech_stopped":
            self._caller_speech_open = False
            return
        if event.type == "delta":
            self._on_caller_words(event.text)
            return
        if event.type == "error":
            await logger.awarning("bridge_stt_error", call_log_id=self.call_log_id, error=event.text)
            return
        if event.type != "completed":
            return
        self._caller_speech_open = False
        text = " ".join(str(event.text or "").split())
        if not text:
            return
        reason = self._phantom_transcript_reason(text)
        if reason:
            await logger.ainfo(reason, call_log_id=self.call_log_id, transcript_preview=text[:160])
            return
        if self.closing:
            await logger.ainfo("ignored_post_closing_transcript", call_log_id=self.call_log_id, transcript_preview=text[:160])
            return
        self._queue_user_turn(text)

    def _phantom_transcript_reason(self, text: str) -> str | None:
        if hearing.is_prompt_echo(text, self._transcription_prompt):
            return "ignored_transcription_prompt_echo"
        now = time.monotonic()
        recent = [line for line, spoken_at in self._recent_agent_lines if now - spoken_at <= 25.0]
        if hearing.echoes_agent_line(text, recent) or self._echoes_short_line(text, now):
            return "ignored_assistant_echo_transcript"
        if hearing.looks_like_noise(text) and not _long_real_speech(text):
            return "ignored_stt_noise_hallucination"
        return None

    def _echoes_short_line(self, text: str, now: float) -> bool:
        """The agent's own ack ("Okay.") heard straight back (too short for hearing's echo check):
        only while it is still the latest line — an "okay" after the next reply is an answer."""
        norm = hearing.normalize(text)
        if not norm or len(norm.split()) > 3 or not self._recent_agent_lines:
            return False
        line, spoken_at = self._recent_agent_lines[-1]
        return now - spoken_at <= SHORT_ECHO_SECONDS and hearing.normalize(line) == norm
