"""Speech-to-text: connecting and reconnecting the STT session, its events, and the
filters that drop phantom transcripts (prompt echo, the agent's own line, noise)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from app.voice.providers.overrides import provider_override
from app.flows import hearing
from app.voice.providers.base import STTSession
from app.voice.providers.stt import open_stt
from app.voice.stt import STTEvent

logger = structlog.get_logger(__name__)


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
        self._stt = await self._open_stt()

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
        stop = "।" if self.primary_language == "bn" else "."
        for hint in self.flow.transcription_hints(self.ctx):
            value = " ".join(str(hint or "").split())[:120]
            if value and value not in parts:
                parts.append(f"{value}{stop}")
        return " ".join(parts)[:900].strip()

    async def _stt_loop(self) -> None:
        reconnects = 0
        while not self.closed:
            stt = self._stt
            if stt is not None:
                async for event in stt.events():
                    if self.closed:
                        return
                    if event.type == "closed":
                        break
                    try:
                        await self._on_stt_event(event)
                    except Exception as exc:  # noqa: BLE001 — one bad event must not deafen the call
                        await logger.awarning("bridge_stt_event_failed", call_log_id=self.call_log_id, error=str(exc))
                if self.closed:
                    return
            reconnects += 1
            if reconnects > 3:
                await logger.awarning("bridge_stt_gave_up", call_log_id=self.call_log_id)
                await self._safe_close()
                return
            await logger.awarning("bridge_stt_reconnecting", call_log_id=self.call_log_id, attempt=reconnects, provider=getattr(stt, "name", ""))
            if stt is not None:
                await stt.close()
                self._retire_stt(stt)
                self._stt = None
            try:
                # The chain walk skips a provider that just failed (paused), so a dead
                # provider hands the call to the next one instead of retrying itself.
                self._stt = await self._open_stt()
            except Exception as exc:  # noqa: BLE001
                await logger.awarning("bridge_stt_reconnect_failed", call_log_id=self.call_log_id, error=str(exc))
                await asyncio.sleep(0.5)

    async def _on_stt_event(self, event: STTEvent) -> None:
        if event.type == "speech_started":
            self._silence_strikes = 0
            self.last_customer_audio_at = time.monotonic()
            if self.assistant_speaking and self._barge_in_allowed and self._barge_in_loud_frames >= self.settings.voice_barge_in_min_frames:
                await self._on_barge_in()
            return
        if event.type == "error":
            await logger.awarning("bridge_stt_error", call_log_id=self.call_log_id, error=event.text)
            return
        if event.type != "completed":
            return
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
        if hearing.echoes_agent_line(text, recent):
            return "ignored_assistant_echo_transcript"
        if hearing.looks_like_noise(text):
            return "ignored_stt_noise_hallucination"
        return None
