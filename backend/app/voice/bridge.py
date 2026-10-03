"""Audio transport for one call: Telnyx media streaming (or the browser test console).

One ``CallBridge`` owns one media websocket and plugs it into a
:class:`~app.voice.agent.CallAgent`:

    caller μ-law ──▶ TranscriptionStream (server VAD, gpt-4o-mini-transcribe)
                          │ completed caller turns
                          ▼
                     CallAgent (flow + tools + gpt-5.4-mini)
                          │ lines to speak
                          ▼
                     AzureSpeechTTS (μ-law 8 kHz, LRU-cached) ──▶ caller

Telnyx (bidirectional RTP mode) and the browser test console speak the same
event set (``start`` / ``media`` / ``mark`` / ``clear`` / ``stop``), so a test
call exercises exactly the production path. The console uses Twilio's field
names (``streamSid``, camelCase) and also gets ``transcript`` and ``state``
events; Telnyx frames carry no stream id.

Turn design
-----------
* **Speaking** is serialized through one speaker task fed by a queue of
  ``_Utterance`` objects. Text is cut into TTS units, synthesized (two in
  flight) and paced to the caller in 20 ms frames ~0.6 s ahead of real time, so
  a ``clear`` on barge-in cuts the line within half a second. A ``mark`` after
  the last frame tells us when the caller actually finished hearing the line —
  that drives the transcript, the silence watchdog and the post-goodbye hangup.
* **Hearing** is half-duplex while the agent speaks: only *sustained* loud
  caller audio (a real interruption) reaches the STT, and that same crossing
  interrupts playback. Scripted lines (greeting, closings) are protected.
* **Caller turns** arrive as ``completed`` STT events, are merged over a short
  window (longer on steps that expect a long answer — an address, a phone
  number), filtered against echo / prompt echo / noise, and answered one at a
  time by the agent.
* **Silence** is two-strike: after ``silence_hangup_secs`` of idle the agent
  asks whether the caller can hear it; the same again and the call is settled
  as ``auto_dropped`` (record → ``no_answer``, callable again).
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.regions import region_of
from app.flows import hearing
from app.flows.base import OUTCOME_AUTO_DROPPED, OUTCOME_DIVERTED, OUTCOME_UNCLEAR, Flow
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext
from app.voice import prepared
from app.voice.agent import CallAgent
from app.voice.audio import (
    FRAME_BYTES,
    FRAME_SECONDS,
    AmbientNoiseTracker,
    clean_spoken_text,
    goodbye_hangup_delay_seconds,
    pcm_rms,
    sentence_units,
    speech_units,
    trim_ulaw_silence,
)
from app.voice.languages import ack_lines, normalize_supported, phrase
from app.voice.llm import ChatLLM
from app.voice.prompts import transcription_prompt
from app.voice.stt import STTEvent, TranscriptionStream
from app.voice.tools import CallStore
from app.voice.tts import TTSError, get_tts, normalize_persona, voice_for

logger = structlog.get_logger(__name__)

# How far ahead of real time outbound audio may run.
PLAYOUT_LEAD_SECONDS = 0.6
# Back-to-back ``completed`` STT events inside this window are one caller turn.
TURN_MERGE_SECONDS = 0.4
# ...and on steps that expect a long answer (address, phone number, problem).
LONG_TURN_MERGE_SECONDS = 1.1
# Persist the transcript every N caller turns (and always at the end).
TRANSCRIPT_SAVE_EVERY = 3


@dataclass
class _Utterance:
    text: str
    allow_barge_in: bool = True
    message_ref: dict[str, Any] | None = None
    close_after: bool = False
    transfer_to: str = ""
    interrupted: bool = False
    spoken_text: str = ""
    done: asyncio.Event = field(default_factory=asyncio.Event)


class CallBridge:
    def __init__(
        self,
        websocket: WebSocket,
        *,
        merchant: Any,
        call_log_id: str,
        stream_sid: str | None,
        order: Any | None = None,
        call_sid: str | None = None,
        store: CallStore | None = None,
        flow: Flow | None = None,
        ctx: CallContext | None = None,
        direction: str = DIRECTION_OUTBOUND,
        caller_number: str = "",
        web: bool = False,
    ) -> None:
        self.websocket = websocket
        self.settings = get_settings()
        self.order = order
        self.merchant = merchant
        self.call_log_id = str(call_log_id)
        self.stream_sid = stream_sid
        self.call_sid = call_sid or ""
        self.web = web
        self.direction = direction
        if ctx is None:
            ctx = CallContext(merchant=merchant, record=order, direction=direction, caller_number=caller_number, test=web)
        self.ctx = ctx
        if flow is None:
            from app.verticals import flow_for

            flow = flow_for(merchant, ctx.direction)
        self.flow = flow
        if store is None:
            from app.services.call_service import DbCallStore

            store = DbCallStore(order_id=str(getattr(order, "id", "") or ""), call_log_id=self.call_log_id, merchant_id=str(getattr(merchant, "id", "") or ""))
        self.store = store

        # --- language / voice ---
        self.primary_language = normalize_supported(getattr(merchant, "language", None), [])[0]
        # The account's language is THE call language: no per-turn auto-detect
        # (one mis-transcribed line used to flip a Bangla call to English).
        self.supported_languages = [self.primary_language]
        self.active_language = self.primary_language
        self.persona = normalize_persona(getattr(merchant, "voice_persona", None) or self.settings.tts_voice_persona)
        self.voice = voice_for(self.persona, self.primary_language, region_of(merchant).accent)
        self._transcription_prompt = transcription_prompt(self.supported_languages)
        self._transcription_language: str | None = self.primary_language

        # --- conversation ---
        # Transport state the agent reads/writes (Speaker protocol).
        self.closed = False
        self.closing = False
        self.assistant_speaking = False
        self.agent = CallAgent(
            flow=self.flow,
            ctx=self.ctx,
            store=self.store,
            speaker=self,
            language=self.primary_language,
            settings=self.settings,
            call_log_id=self.call_log_id,
            support_phone=str(getattr(merchant, "support_phone", "") or ""),
        )
        self.transcript_lines: list[tuple[str, str]] = []
        self._recent_agent_lines: deque[tuple[str, float]] = deque(maxlen=8)
        self._transcript_saved_turns = 0
        self._turn_started_at = 0.0
        self._turn_first_audio_logged = True

        # --- caller-turn merge + agent-turn serialization ---
        self._pending_user_turn_text = ""
        self._pending_user_turn_task: asyncio.Task[None] | None = None
        self._pending_user_turn_seq = 0
        self._turn_backlog = ""
        self._agent_turn_task: asyncio.Task[None] | None = None

        # --- audio out ---
        self._speech_queue: asyncio.Queue[_Utterance] = asyncio.Queue()
        self._speaker_task: asyncio.Task[None] | None = None
        self._current_utterance: _Utterance | None = None
        self._barge_in_allowed = True
        self._assistant_turn_started_at = 0.0
        self._playout_end = 0.0
        self._mark_counter = 0
        self._pending_playback_mark: str | None = None
        self._playback_mark_event = asyncio.Event()
        self._tts_semaphore = asyncio.Semaphore(2)
        self.tts_chars = 0
        self.tts_cache_hits = 0

        # --- audio in / barge-in ---
        self._ambient_noise = AmbientNoiseTracker()
        self._barge_in_window: deque[int] = deque(maxlen=max(2, self.settings.voice_barge_in_min_frames * 2))
        self._barge_in_loud_frames = 0
        self._barge_in_prebuffer: deque[str] = deque(maxlen=50)
        self._last_barge_in_at = 0.0

        # --- watchdog / lifecycle ---
        self.started_at = time.monotonic()
        self.last_customer_audio_at = self.started_at
        self.last_voice_activity_at = self.started_at
        self._silence_counting_paused_until = 0.0
        self._silence_strikes = 0
        self._hangup_scheduled = False
        self._goodbye_hangup_delay_seconds = 8.0
        self._goodbye_playback_tail_seconds = 1.5
        self._closed_by_agent = False
        self._finalized = False

        # --- pipeline components (created in run) ---
        self._stt: TranscriptionStream | None = None
        self._llm: ChatLLM | None = None

    # ------------------------------------------------------------------ agent views
    @property
    def runtime(self):
        return self.agent.runtime

    @property
    def tools(self):
        return self.agent.tools

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self.agent.messages

    @property
    def outcome(self) -> str:
        return self.agent.outcome

    # ------------------------------------------------------------------ limits
    @property
    def max_call_seconds(self) -> int:
        configured = int(getattr(self.merchant, "max_call_seconds", 0) or 0)
        if configured > 0:
            return configured
        if self.ctx.direction == DIRECTION_INBOUND:
            return int(self.settings.voice_max_inbound_call_seconds)
        return int(self.settings.voice_max_call_seconds)

    @property
    def silence_seconds(self) -> int:
        return max(3, int(getattr(self.merchant, "silence_hangup_secs", 0) or 10))

    # ------------------------------------------------------------------ bootstrap
    async def run(self) -> None:
        try:
            if not self.settings.openai_api_key:
                await logger.awarning("bridge_missing_openai_api_key", call_log_id=self.call_log_id)
                await self._safe_close(code=1011)
                return
            if not self.settings.azure_speech_key:
                await logger.awarning("bridge_missing_azure_speech_key", call_log_id=self.call_log_id)
                await self._safe_close(code=1011)
                return
            tasks: list[asyncio.Task[None]] = []
            try:
                self.agent.settings = self.settings
                self._refresh_prepared()
                opening = self.agent.configure()
                self._llm = ChatLLM(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.openai_llm_model,
                    reasoning_effort=self.settings.openai_llm_reasoning_effort,
                    max_output_tokens=self.settings.openai_llm_max_output_tokens,
                    prompt_cache_key=f"{self.flow.key}:{getattr(self.merchant, 'id', '')}",
                    prompt_cache_retention=self.settings.openai_prompt_cache_retention,
                )
                self.agent.llm = self._llm
                # Greet FIRST — the opening is already in the TTS cache — and open the
                # transcription socket while it plays. The caller must hear a voice
                # within a second of answering; nothing else is allowed in front of it.
                self._turn_started_at = time.monotonic()
                self._turn_first_audio_logged = False
                self._speaker_task = asyncio.create_task(self._speaker_loop())
                self.speak(opening, allow_barge_in=False, message_ref=self.messages[-1])
                media_task = asyncio.create_task(self._media_loop())
                self._stt = self._new_stt()
                stt_connect = asyncio.create_task(self._stt.connect())
                asyncio.create_task(self._warm_tts_cache())
                if self.settings.voice_hangup_on_forwarded and self.call_sid and self.ctx.direction == DIRECTION_OUTBOUND:
                    asyncio.create_task(self._check_diverted())
                await stt_connect
                logger.info("bridge_stt_connected", call_log_id=self.call_log_id, ms=int((time.monotonic() - self._turn_started_at) * 1000))
                await self._emit_state()
                tasks = [
                    media_task,
                    asyncio.create_task(self._stt_loop()),
                    asyncio.create_task(self._watchdog()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                self.closed = True
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    if not task.cancelled() and task.exception() is not None:
                        raise task.exception()  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001
                await logger.awarning("bridge_failed", call_log_id=self.call_log_id, error=str(exc), error_type=type(exc).__name__)
                await self._safe_close()
        finally:
            await self._teardown()

    def _refresh_prepared(self) -> None:
        """Lines composed while the phone rang (outbound) — picked up as soon as they exist."""
        record_id = str(getattr(self.order, "id", "") or "")
        if not record_id:
            return
        line = prepared.get_decision_line(record_id, self.primary_language)
        if line:
            self.ctx.prepared["decision"] = line

    def _new_stt(self) -> TranscriptionStream:
        return TranscriptionStream(
            api_key=str(self.settings.openai_api_key or ""),
            model=self.settings.openai_transcription_model,
            language=self._transcription_language,
            prompt=self._stt_prompt(),
            vad_threshold=self.settings.stt_vad_threshold,
            vad_prefix_padding_ms=self.settings.stt_vad_prefix_padding_ms,
            vad_silence_duration_ms=self.settings.stt_vad_silence_duration_ms,
            noise_reduction=self.settings.openai_noise_reduction,
        )

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

    async def _warm_tts_cache(self) -> None:
        try:
            tts = get_tts()
            for language in self.supported_languages:
                lines = list(self.flow.prefetch_lines(self.ctx, language)) + list(ack_lines(language))
                count = await tts.warm(sentence_units(lines), language=language, persona=self.persona, voice=self.voice)
                if count:
                    await logger.ainfo("tts_cache_warmed", call_log_id=self.call_log_id, language=language, synthesized=count)
        except Exception as exc:  # noqa: BLE001 — warming is an optimization only
            await logger.awarning("tts_cache_warm_failed", call_log_id=self.call_log_id, error=str(exc))

    async def _check_diverted(self) -> None:
        """Hang up when the carrier forwarded the call (reject → voicemail / divert).

        A rejected or busy callee is often forwarded by the network to a voicemail
        or "call back" service that answers as if it were a person; the provider marks
        such calls with ``forwarded_from`` (Telnyx doesn't report it, so this is a no-op there). Talking to it wastes minutes, so the
        call is dropped right away and the record goes back to ``no_answer``.
        """
        from app.services.call_service import fetch_call_details

        try:
            details = await fetch_call_details(self.call_sid)
        except Exception as exc:  # noqa: BLE001 — a lookup failure just means no shortcut
            await logger.ainfo("call_lookup_failed", call_log_id=self.call_log_id, error=str(exc))
            return
        forwarded = str(details.get("forwarded_from") or "").strip()
        if not forwarded or self.closed:
            return
        # Some carriers stamp forwarded_from with the dialed number itself on
        # ordinary answered calls; only a forward to a DIFFERENT number is a divert.
        from app.core.regions import normalize_phone

        region = region_of(self.merchant)
        dialed = normalize_phone(str(getattr(self.order, "customer_phone", "") or ""), region)
        if not dialed or normalize_phone(forwarded, region) == dialed:
            return
        await logger.ainfo(
            "call_diverted_hangup",
            call_log_id=self.call_log_id,
            forwarded_from=forwarded,
            answered_by=details.get("answered_by"),
        )
        self.closing = True
        await self._interrupt_playback("diverted")
        await self.agent.abandon(OUTCOME_DIVERTED)
        await self._safe_close()

    async def _teardown(self) -> None:
        self.closed = True
        for task in (self._pending_user_turn_task, self._speaker_task, self._agent_turn_task):
            if task and not task.done():
                task.cancel()
        if self._stt is not None:
            await self._stt.close()
        await self._finalize()
        if self._llm is not None:
            await self._llm.aclose()

    async def _finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        try:
            if not self.outcome and self.ctx.direction == DIRECTION_INBOUND:
                # The caller hung up first: keep what they told us when the flow can
                # use it (a partial lead), otherwise it was an enquiry.
                await self.agent.tools.finish_inbound()
            await self._persist_transcript(force=True)
            counters = {
                "tts_chars": self.tts_chars,
                "tts_cache_hits": self.tts_cache_hits,
                "duration_secs": int(time.monotonic() - self.started_at),
            }
            if self._llm is not None:
                counters["llm_prompt_tokens"] = int(self._llm.prompt_tokens)
                counters["llm_completion_tokens"] = int(self._llm.completion_tokens)
                counters["llm_cached_tokens"] = int(self._llm.cached_prompt_tokens)
            await self.store.save_usage(**counters)
            notify = getattr(self.store, "notify_finished", None)
            if notify is not None:
                await notify()
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("bridge_finalize_failed", call_log_id=self.call_log_id, error=str(exc))
        await logger.ainfo(
            "call_finished",
            call_log_id=self.call_log_id,
            flow=self.flow.key,
            outcome=self.outcome,
            final_node=self.runtime.current_node,
            duration_seconds=int(time.monotonic() - self.started_at),
            turns=self.agent.turns,
            fast_turns=self.agent.fast_turns,
            llm=self._llm.stats() if self._llm is not None else {},
        )

    # ------------------------------------------------------------------ media in
    def _frame(self, event: str, **body: Any) -> dict[str, Any]:
        """An outgoing media-socket event: the console wants ``streamSid``; Telnyx
        rejects unknown fields."""
        message: dict[str, Any] = {"event": event, **body}
        if self.web:
            message["streamSid"] = self.stream_sid
        return message

    async def _media_loop(self) -> None:
        while not self.closed:
            try:
                message = await self.websocket.receive_json()
            except (WebSocketDisconnect, RuntimeError) as exc:
                if not self.closed:
                    await logger.ainfo("media_disconnected", call_log_id=self.call_log_id, detail=str(exc)[:120])
                self.closed = True
                if self._stt is not None:
                    await self._stt.close()
                return
            event = message.get("event")
            if event == "start":
                start = message.get("start") or {}
                self.stream_sid = message.get("stream_id") or start.get("streamSid") or self.stream_sid
                self.call_sid = start.get("call_control_id") or start.get("callSid") or self.call_sid
            elif event == "media":
                payload = (message.get("media") or {}).get("payload") or ""
                if payload:
                    await self._handle_inbound_frame(payload)
            elif event == "mark":
                mark_name = str(((message.get("mark") or {}).get("name")) or "").strip()
                if mark_name and mark_name == self._pending_playback_mark:
                    self._pending_playback_mark = None
                    self._playback_mark_event.set()
            elif event == "error":
                await logger.awarning("media_stream_error", call_log_id=self.call_log_id, error=message.get("payload"))
            elif event == "stop":
                self.closed = True
                if self._stt is not None:
                    await self._stt.close()
                break

    async def _handle_inbound_frame(self, payload: str) -> None:
        stt = self._stt
        rms = pcm_rms(payload)
        if not self.assistant_speaking:
            self._ambient_noise.update(rms)
        cap = 3200
        speech_gate = self._ambient_noise.gate(self.settings.voice_speech_start_min_rms, 2.0, cap)
        barge_gate = self._ambient_noise.gate(self.settings.voice_barge_in_min_rms, 2.5, cap)
        if rms >= speech_gate:
            self.last_customer_audio_at = time.monotonic()
            self.last_voice_activity_at = self.last_customer_audio_at
        if not self.assistant_speaking:
            self._barge_in_loud_frames = 0
            if self._barge_in_prebuffer:
                if sum(self._barge_in_window) >= 2 and stt is not None:
                    for buffered in self._barge_in_prebuffer:
                        await stt.send_audio_b64(buffered)
                self._barge_in_prebuffer.clear()
            self._barge_in_window.clear()
            if stt is not None:
                await stt.send_audio_b64(payload)
            return
        # Half duplex: only SUSTAINED loud audio (a real barge-in) reaches the STT.
        self._barge_in_window.append(1 if rms >= barge_gate else 0)
        self._barge_in_loud_frames = sum(self._barge_in_window)
        if self._barge_in_loud_frames < self.settings.voice_barge_in_min_frames:
            self._barge_in_prebuffer.append(payload)
            return
        self._barge_in_window.clear()
        if stt is not None:
            for buffered in self._barge_in_prebuffer:
                await stt.send_audio_b64(buffered)
        self._barge_in_prebuffer.clear()
        await self._on_barge_in()
        if stt is not None:
            await stt.send_audio_b64(payload)

    async def _on_barge_in(self) -> None:
        self._last_barge_in_at = time.monotonic()
        self._silence_strikes = 0
        if not self._barge_in_allowed:
            return
        await self._interrupt_playback("caller_barge_in")

    # ------------------------------------------------------------------ STT in
    async def _stt_loop(self) -> None:
        reconnects = 0
        while not self.closed:
            stt = self._stt
            if stt is None:
                return
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
            await logger.awarning("bridge_stt_reconnecting", call_log_id=self.call_log_id, attempt=reconnects)
            await stt.close()
            try:
                self._stt = self._new_stt()
                await self._stt.connect()
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

    # ------------------------------------------------------------------ caller turns
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

    # ------------------------------------------------------------------ audio out
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

    async def _synthesize(self, text: str, language: str) -> bytes:
        async with self._tts_semaphore:
            tts = get_tts()
            try:
                cache = getattr(tts, "cache", None)
                if cache is not None and hasattr(tts, "cache_key") and cache.contains(tts.cache_key(text, voice=self.voice)):
                    self.tts_cache_hits += 1
                else:
                    self.tts_chars += len(text)
            except Exception:  # noqa: BLE001 — stats only
                pass
            try:
                return await tts.synthesize(text, language=language, persona=self.persona, voice=self.voice)
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

    def _record_assistant_transcript(self, text: str) -> None:
        text = " ".join(str(text or "").split())
        if not text:
            return
        if self.transcript_lines and self.transcript_lines[-1] == ("Agent", text):
            return
        self.transcript_lines.append(("Agent", text))
        if self.web:
            asyncio.create_task(self._emit({"event": "transcript", "role": "agent", "text": text}))

    def transcript_text(self) -> str:
        return "\n".join(f"{role}: {text}" for role, text in self.transcript_lines)

    async def _persist_transcript(self, *, force: bool = False) -> None:
        if not force and self.agent.turns - self._transcript_saved_turns < TRANSCRIPT_SAVE_EVERY:
            return
        if not self.transcript_lines:
            return
        self._transcript_saved_turns = self.agent.turns
        try:
            await self.store.save_transcript(self.transcript_text(), language=self.active_language, final_node=self.runtime.current_node)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("transcript_persist_failed", call_log_id=self.call_log_id, error=str(exc))

    # ------------------------------------------------------------------ test console events
    async def _emit(self, message: dict[str, Any]) -> None:
        """Extra events for the browser test console (never sent to Telnyx)."""
        if not self.web or self.closed:
            return
        try:
            await self.websocket.send_json(message)
        except Exception:  # noqa: BLE001
            pass

    async def _emit_state(self) -> None:
        await self._emit({"event": "state", **self.agent.state()})

    # ------------------------------------------------------------------ watchdog / lifecycle
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

    def _schedule_hangup(self, utterance: _Utterance | None) -> None:
        if self._hangup_scheduled:
            return
        self._hangup_scheduled = True
        asyncio.create_task(self._close_after_goodbye(utterance))

    async def _close_after_goodbye(self, utterance: _Utterance | None) -> None:
        if utterance is not None:
            try:
                await asyncio.wait_for(utterance.done.wait(), timeout=self._goodbye_hangup_delay_seconds + 5.0)
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(self._goodbye_playback_tail_seconds)
        if not self.closed:
            await self._emit({"event": "hangup", **self.agent.state()})
            await self._safe_close()

    async def _transfer_call(self, number: str) -> None:
        """Dial the business's support line once the transfer line has played."""
        await asyncio.sleep(0.3)
        try:
            ok = await self._dial_support(number)
        except Exception as exc:  # noqa: BLE001
            ok = False
            await logger.awarning("transfer_dial_failed", call_log_id=self.call_log_id, error=str(exc))
        if ok:
            await logger.ainfo("transfer_started", call_log_id=self.call_log_id, target=number)
            # Telnyx ends the stream when the call moves to <Dial>; close our side too.
            await asyncio.sleep(2.0)
            await self._safe_close(end_phone_call=False)
            return
        line = phrase("closing_transfer_callback", self.active_language)
        self.messages.append({"role": "assistant", "content": line})
        self.speak(line, allow_barge_in=False, close_after=True)

    async def _dial_support(self, number: str) -> bool:
        from app.services import telnyx
        from app.services.call_service import redirect_call_to_human

        if not self.call_sid or self.web:
            return False
        return await redirect_call_to_human(self.call_sid, number, region_of(self.merchant), caller_id=telnyx.number_for(self.merchant))

    async def _end_phone_call(self) -> None:
        if not self.call_sid or self.web:
            return
        from app.services.call_service import complete_call

        try:
            await complete_call(self.call_sid)
        except Exception as exc:  # noqa: BLE001
            await logger.ainfo("complete_call_failed", call_log_id=self.call_log_id, error=str(exc))

    async def _safe_close(self, *, code: int | None = None, end_phone_call: bool = True) -> None:
        self._closed_by_agent = True
        already_closed = self.closed
        self.closed = True
        try:
            if code is not None:
                await self.websocket.close(code=code)
            else:
                await self.websocket.close()
        except Exception:  # noqa: BLE001
            pass
        if end_phone_call and not already_closed:
            await self._end_phone_call()


__all__ = ["CallBridge"]
