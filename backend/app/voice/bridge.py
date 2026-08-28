"""Per-call orchestrator for one outbound confirmation call.

One ``ConfirmationCallBridge`` owns one Twilio Media Stream:

    Twilio μ-law ──▶ TranscriptionStream (server VAD, gpt-4o-mini-transcribe)
                          │ completed caller turns
                          ▼
                     ChatLLM (gpt-5.4-mini + flow tools) ──▶ CallTools
                          │ text / verbatim lines
                          ▼
                     AzureSpeechTTS (μ-law 8 kHz, LRU-cached) ──▶ Twilio

Turn design
-----------
* **Speaking** is serialized through one speaker task fed by a queue of
  ``_Utterance`` objects. Text is split into sentences, each sentence is
  synthesized (two in flight) and paced to Twilio in 20 ms frames ~0.6 s ahead
  of real time, so a ``clear`` on barge-in cuts the line within half a second.
  A Twilio ``mark`` after the last frame tells us when the caller actually
  finished hearing the line — that drives the transcript, the silence watchdog
  and the post-goodbye hangup.
* **Hearing** is half-duplex while the agent speaks: only *sustained* loud
  caller audio (a real interruption) reaches the STT, and that same crossing
  interrupts playback. Scripted lines (greeting, closings) are protected.
* **Caller turns** arrive as ``completed`` STT events, are merged over a short
  window, filtered against echo / prompt echo / noise, and answered one at a
  time through the model ↔ tools loop.
* **Silence** is two-strike: after ``merchant.silence_hangup_secs`` of idle the
  agent asks whether the caller can hear it; the same again and the call is
  settled as ``auto_dropped`` (order → ``no_answer``, callable again).
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.flows import hearing
from app.flows.base import OUTCOME_AUTO_DROPPED, OUTCOME_DIVERTED, OUTCOME_UNCLEAR, STAGE_ADDRESS, STAGE_DECISION, STAGE_DONE, STAGE_IDENTITY, STAGE_KNOWS_PERSON, STAGE_RELAY, STAGE_WRONG_NUMBER, Flow
from app.flows.ecommerce import DEFAULT_FLOW
from app.flows.runtime import FlowRuntime
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
from app.voice.languages import detect_language, normalize_supported, phrase
from app.voice.llm import ChatLLM, LLMReply
from app.voice.prompts import build_system_prompt, transcription_prompt
from app.voice import prepared
from app.voice.stt import STTEvent, TranscriptionStream
from app.voice.tools import SAVE_DETAILS, CallStore, CallTools, ToolResult
from app.voice.tts import TTSError, get_tts, normalize_persona

logger = structlog.get_logger(__name__)

# How far ahead of real time outbound audio may run.
PLAYOUT_LEAD_SECONDS = 0.6
# Back-to-back ``completed`` STT events inside this window are one caller turn.
TURN_MERGE_SECONDS = 0.4
# Max model ↔ tool hops per caller turn.
MAX_TOOL_HOPS = 6
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


class ConfirmationCallBridge:
    def __init__(
        self,
        websocket: WebSocket,
        *,
        order: Any,
        merchant: Any,
        call_log_id: str,
        stream_sid: str | None,
        call_sid: str | None = None,
        store: CallStore | None = None,
        flow: Flow | None = None,
    ) -> None:
        self.websocket = websocket
        self.settings = get_settings()
        self.order = order
        self.merchant = merchant
        self.call_log_id = str(call_log_id)
        self.stream_sid = stream_sid
        self.call_sid = call_sid or ""
        self.flow = flow or DEFAULT_FLOW
        if store is None:
            from app.services.call_service import DbCallStore

            store = DbCallStore(order_id=str(getattr(order, "id", "")), call_log_id=self.call_log_id)
        self.store = store

        # --- language / voice ---
        self.primary_language = normalize_supported(getattr(merchant, "language", None), [])[0]
        self.supported_languages = normalize_supported(self.primary_language, getattr(merchant, "supported_languages", None))
        self.active_language = self.primary_language
        self.persona = normalize_persona(getattr(merchant, "voice_persona", None) or self.settings.tts_voice_persona)
        self._transcription_prompt = transcription_prompt(self.supported_languages)
        self._transcription_language: str | None = self.supported_languages[0] if len(self.supported_languages) == 1 else None

        # --- conversation ---
        self.runtime = FlowRuntime(self.flow, order, merchant, language=self.primary_language, on_directive=self._on_directive)
        self.tools = CallTools(self.runtime, self.store, support_phone=str(getattr(merchant, "support_phone", "") or ""))
        self.messages: list[dict[str, Any]] = []
        # Node directives raised while a tool runs; appended only AFTER the tool
        # reply, because Chat Completions requires the tool message to directly
        # follow the assistant message that called it.
        self._pending_directives: list[str] = []
        self.current_tools: list[dict[str, Any]] = self.tools.schemas()
        self.transcript_lines: list[tuple[str, str]] = []
        self._last_user_text = ""
        self._recent_agent_lines: deque[tuple[str, float]] = deque(maxlen=8)
        self._turn_counter = 0
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
        self.assistant_speaking = False
        self._barge_in_allowed = True
        self._assistant_turn_started_at = 0.0
        self._playout_end = 0.0
        self._twilio_mark_counter = 0
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
        self._closing = False
        self._hangup_scheduled = False
        self._goodbye_hangup_delay_seconds = 8.0
        self._goodbye_playback_tail_seconds = 1.5
        self.closed = False
        self._closed_by_agent = False
        self._finalized = False

        # --- pipeline components (created in run) ---
        self._stt: TranscriptionStream | None = None
        self._llm: ChatLLM | None = None

    # ------------------------------------------------------------------ limits
    @property
    def max_call_seconds(self) -> int:
        configured = int(getattr(self.merchant, "max_call_seconds", 0) or 0)
        return configured if configured > 0 else int(self.settings.voice_max_call_seconds)

    @property
    def silence_seconds(self) -> int:
        return max(3, int(getattr(self.merchant, "silence_hangup_secs", 0) or 10))

    @property
    def outcome(self) -> str:
        return self.tools.outcome

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
                self._configure()
                self._llm = ChatLLM(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.openai_llm_model,
                    reasoning_effort=self.settings.openai_llm_reasoning_effort,
                    max_output_tokens=self.settings.openai_llm_max_output_tokens,
                )
                self._stt = self._new_stt()
                await self._stt.connect()
                asyncio.create_task(self._warm_tts_cache())
                if self.settings.voice_hangup_on_forwarded and self.call_sid:
                    asyncio.create_task(self._check_diverted())
                self._speaker_task = asyncio.create_task(self._speaker_loop())
                opening = f"{self.runtime.greeting()} {self.runtime.opening_question()}"
                self.speak(opening, allow_barge_in=False, message_ref=self.messages[-1] if self.messages and self.messages[-1]["role"] == "assistant" else None)
                tasks = [
                    asyncio.create_task(self._twilio_loop()),
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

    def _configure(self) -> None:
        directive = self.runtime.initial_directive()
        system = build_system_prompt(
            self.order, self.merchant, self.flow, language=self.primary_language, initial_directive=directive
        )
        self.messages = [{"role": "system", "content": system}]
        # The greeting + first question are spoken by the bridge; the model sees them as its own words.
        self.messages.append({"role": "assistant", "content": f"{self.runtime.greeting()} {self.runtime.opening_question()}"})

    def _on_directive(self, directive: str) -> None:
        if self.messages:
            self._pending_directives.append(directive)

    def _flush_directives(self) -> None:
        for directive in self._pending_directives:
            self.messages.append({"role": "system", "content": directive})
        self._pending_directives.clear()

    def _new_stt(self) -> TranscriptionStream:
        return TranscriptionStream(
            api_key=str(self.settings.openai_api_key or ""),
            model=self.settings.openai_transcription_model,
            language=self._transcription_language,
            prompt=self._transcription_prompt,
            vad_threshold=self.settings.stt_vad_threshold,
            vad_prefix_padding_ms=self.settings.stt_vad_prefix_padding_ms,
            vad_silence_duration_ms=self.settings.stt_vad_silence_duration_ms,
            noise_reduction=self.settings.openai_noise_reduction,
        )

    async def _warm_tts_cache(self) -> None:
        try:
            tts = get_tts()
            for language in self.supported_languages:
                lines = sentence_units(self.flow.prefetch_lines(self.order, self.merchant, language))
                count = await tts.warm(lines, language=language, persona=self.persona)
                if count:
                    await logger.ainfo("tts_cache_warmed", call_log_id=self.call_log_id, language=language, synthesized=count)
        except Exception as exc:  # noqa: BLE001 — warming is an optimization only
            await logger.awarning("tts_cache_warm_failed", call_log_id=self.call_log_id, error=str(exc))

    async def _check_diverted(self) -> None:
        """Hang up when the carrier forwarded the call (reject → voicemail / divert).

        A rejected or busy callee is often forwarded by the network to a voicemail
        or "call back" service that answers as if it were a person; Twilio marks
        such calls with ``forwarded_from``. Talking to it wastes minutes and can
        make the customer's phone ring again, so the call is dropped right away
        and the order goes back to ``no_answer``.
        """
        from app.services.call_service import fetch_call_details

        try:
            details = await fetch_call_details(self.call_sid)
        except Exception as exc:  # noqa: BLE001 — a lookup failure just means no shortcut
            await logger.ainfo("twilio_call_lookup_failed", call_log_id=self.call_log_id, error=str(exc))
            return
        forwarded = str(details.get("forwarded_from") or "").strip()
        if not forwarded or self.closed:
            return
        # Some carriers/Twilio stamp forwarded_from with the dialed number itself on
        # ordinary answered calls; only a forward to a DIFFERENT number is a divert.
        from app.services.call_service import normalize_bd_phone

        dialed = normalize_bd_phone(str(getattr(self.order, "customer_phone", "") or ""))
        if not dialed or normalize_bd_phone(forwarded) == dialed:
            return
        await logger.ainfo(
            "call_diverted_hangup",
            call_log_id=self.call_log_id,
            forwarded_from=forwarded,
            answered_by=details.get("answered_by"),
        )
        self._closing = True
        await self._interrupt_playback("diverted")
        await self.tools.abandon(OUTCOME_DIVERTED)
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
            await self._persist_transcript(force=True)
            counters = {"tts_chars": self.tts_chars, "tts_cache_hits": self.tts_cache_hits}
            if self._llm is not None:
                counters["llm_prompt_tokens"] = int(self._llm.prompt_tokens)
                counters["llm_completion_tokens"] = int(self._llm.completion_tokens)
            await self.store.save_usage(**counters)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("bridge_finalize_failed", call_log_id=self.call_log_id, error=str(exc))
        await logger.ainfo(
            "confirmation_call_finished",
            call_log_id=self.call_log_id,
            outcome=self.outcome,
            final_node=self.runtime.current_node,
            duration_seconds=int(time.monotonic() - self.started_at),
            turns=self._turn_counter,
            llm=self._llm.stats() if self._llm is not None else {},
        )

    # ------------------------------------------------------------------ Twilio in
    async def _twilio_loop(self) -> None:
        while not self.closed:
            try:
                message = await self.websocket.receive_json()
            except (WebSocketDisconnect, RuntimeError) as exc:
                if not self.closed:
                    await logger.ainfo("twilio_media_disconnected", call_log_id=self.call_log_id, detail=str(exc)[:120])
                self.closed = True
                if self._stt is not None:
                    await self._stt.close()
                return
            event = message.get("event")
            if event == "start":
                start = message.get("start") or {}
                self.stream_sid = start.get("streamSid") or self.stream_sid
                self.call_sid = start.get("callSid") or self.call_sid
            elif event == "media":
                payload = (message.get("media") or {}).get("payload") or ""
                if payload:
                    await self._handle_inbound_frame(payload)
            elif event == "mark":
                mark_name = str(((message.get("mark") or {}).get("name")) or "").strip()
                if mark_name and mark_name == self._pending_playback_mark:
                    self._pending_playback_mark = None
                    self._playback_mark_event.set()
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
        if self._closing:
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
    def _queue_user_turn(self, text: str) -> None:
        self._pending_user_turn_text = " ".join(f"{self._pending_user_turn_text} {text}".split())
        self._pending_user_turn_seq += 1
        seq = self._pending_user_turn_seq
        if self._pending_user_turn_task and not self._pending_user_turn_task.done():
            self._pending_user_turn_task.cancel()
        self._pending_user_turn_task = asyncio.create_task(self._flush_user_turn_after_delay(seq))

    async def _flush_user_turn_after_delay(self, seq: int) -> None:
        try:
            await asyncio.sleep(TURN_MERGE_SECONDS)
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
        self._last_user_text = text
        self._update_active_language(text)
        self._silence_strikes = 0
        now = time.monotonic()
        self.last_customer_audio_at = now
        self.last_voice_activity_at = now
        self.transcript_lines.append(("Customer", text))

    def _update_active_language(self, caller_text: str) -> None:
        if len(self.supported_languages) < 2:
            return
        detected = detect_language(caller_text, supported=self.supported_languages)
        if not detected or detected == self.active_language:
            return
        previous = self.active_language
        self.active_language = detected
        self.runtime.set_language(detected)
        logger.info("caller_language_switched", call_log_id=self.call_log_id, from_language=previous, to_language=detected)

    def _submit_turn(self, text: str) -> None:
        self._turn_backlog = " ".join(f"{self._turn_backlog} {text}".split())
        if self._agent_turn_task and not self._agent_turn_task.done():
            return
        self._agent_turn_task = asyncio.create_task(self._drain_turns())

    def _agent_turn_running(self) -> bool:
        return bool(self._agent_turn_task and not self._agent_turn_task.done())

    async def _drain_turns(self) -> None:
        while not self.closed and self._turn_backlog and not self._closing:
            text = self._turn_backlog
            self._turn_backlog = ""
            try:
                await self._agent_turn(text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — the line must never go dead
                await logger.awarning("bridge_agent_turn_failed", call_log_id=self.call_log_id, error=str(exc), error_type=type(exc).__name__)
                if not self.closed and not self._closing:
                    self.speak(phrase("recovery", self.active_language))
            await self._persist_transcript()

    # ------------------------------------------------------------------ agent turn
    async def _agent_turn(self, text: str) -> None:
        llm = self._llm
        if llm is None or self.closed:
            return
        self._turn_counter += 1
        self._turn_started_at = time.monotonic()
        self._turn_first_audio_logged = False
        if await self._fast_path(text):
            return
        self._flush_directives()
        self.messages.append({"role": "user", "content": text})
        if self.settings.voice_instant_ack and not self.assistant_speaking and not self._closing:
            # One cached word right away; the real reply queues behind it — but not
            # a "হ্যাঁ" on top of a caller who just said no.
            labels = hearing.classify(text)
            if not labels & {"no", "not_me", "wrong_number", "later", "repeat"}:
                self.speak(phrase("ack", self.active_language))
        for _hop in range(MAX_TOOL_HOPS):
            if self.closed or self._closing:
                return
            llm_started = time.monotonic()
            reply = await llm.complete(self.messages, tools=self.current_tools, temperature=self.settings.openai_llm_temperature)
            logger.info(
                "turn_llm_reply",
                call_log_id=self.call_log_id,
                hop=_hop,
                ms=int((time.monotonic() - llm_started) * 1000),
                tool_calls=[c.name for c in reply.tool_calls],
            )
            if reply.tool_calls:
                self.messages.append(self._assistant_tool_message(reply))
                stop = False
                for call in reply.tool_calls:
                    result = await self._run_tool_call(call.id, call.name, call.arguments)
                    stop = stop or result.stop
                if stop or self.closed or self._closing:
                    return
                continue
            content = clean_spoken_text(reply.content)
            if not content:
                await logger.ainfo("bridge_empty_reply", call_log_id=self.call_log_id, finish_reason=reply.finish_reason)
                line = phrase("recovery", self.active_language)
                self.messages.append({"role": "assistant", "content": line})
                self.speak(line)
                return
            message = reply.assistant_message or {"role": "assistant", "content": content}
            message["content"] = content
            self.messages.append(message)
            self.speak(content, message_ref=message)
            return
        await logger.awarning("bridge_tool_hop_limit", call_log_id=self.call_log_id, hops=MAX_TOOL_HOPS)
        self.speak(phrase("recovery", self.active_language))


    async def _fast_path(self, text: str) -> bool:
        """Answer scripted yes/no steps without the model.

        The identity question and the address check have backend-owned next
        lines, so when the caller's words are unambiguous the slot is saved and
        the next line is spoken straight from the TTS cache — no tool round-trip,
        no narration round-trip. Anything less than a clean answer, and any
        stage the model has to phrase itself without a prepared line, goes the
        normal way.
        """
        stage = self.runtime.stage
        if stage not in (STAGE_IDENTITY, STAGE_KNOWS_PERSON, STAGE_ADDRESS) or self._closing:
            return False
        labels = hearing.classify(text)
        if not labels or "repeat" in labels or "later" in labels or hearing.looks_like_question(text):
            return False
        identity_talk = bool(labels & {"not_me", "knows", "wrong_number"})
        fields: dict[str, Any] | None = None
        if stage == STAGE_IDENTITY:
            if "is_me" in labels and not identity_talk:
                fields = {"identity_confirmed": True}
            elif "wrong_number" in labels:
                fields = {"identity_confirmed": False, "wrong_person": True}
            elif "no" in labels and "is_me" not in labels and hearing.is_pure_answer(text):
                # "না" alone: not them — ask whether they know the customer.
                fields = {"identity_confirmed": False}
        elif stage == STAGE_KNOWS_PERSON:
            if "wrong_number" in labels or ("no" in labels and "knows" not in labels):
                fields = {"knows_customer": False}
            elif "knows" in labels or ("yes" in labels and hearing.is_pure_answer(text)):
                fields = {"knows_customer": True}
        elif stage == STAGE_ADDRESS and hearing.is_pure_answer(text) and not identity_talk:
            if "yes" in labels:
                fields = {"address_correct": True}
            elif "no" in labels:
                fields = {"address_correct": False}
        if not fields:
            return False
        # Decide what would be spoken BEFORE touching the runtime, so a missing
        # prepared line leaves the flow untouched for the model path.
        next_stage = self.flow.next_stage({**self.runtime.slots, **fields}, self.order, self.merchant)
        instruction = self.flow.instruction(next_stage, {**self.runtime.slots, **fields}, self.order, self.merchant, self.active_language)
        line: str | None = None
        close_after = False
        saved = False
        if next_stage in (STAGE_RELAY, STAGE_WRONG_NUMBER):
            # Relay / wrong number: save_details settles the outcome, speaks the
            # closing line and hangs up (see CallTools._save_details).
            result = await self.tools.execute(SAVE_DETAILS, fields, caller_text=text)
            if not result.say:
                return False
            self.messages.append({"role": "user", "content": text})
            self._flush_directives()
            message = {"role": "assistant", "content": result.say}
            self.messages.append(message)
            logger.info("turn_fast_path", call_log_id=self.call_log_id, stage=stage, next_stage=self.runtime.stage, saved=sorted(fields), closing=True)
            self._closing = True
            self.speak(result.say, message_ref=message, allow_barge_in=False, close_after=bool(result.hang_up))
            return True
        if next_stage == STAGE_DECISION:
            line = prepared.get_decision_line(str(getattr(self.order, "id", "")), self.active_language)
        elif next_stage == STAGE_DONE and self.tools.outcome and not self.tools.closing_spoken:
            # Address confirmed after the yes: save it, then nothing is left but the goodbye.
            self.runtime.save(fields)
            saved = True
            line = (await self.tools.closing_result()).say
            close_after = True
        elif instruction.verbatim and not instruction.end_call:
            line = instruction.text
        if not line:
            return False
        if not saved:
            self.runtime.save(fields)
        self.messages.append({"role": "user", "content": text})
        self._flush_directives()
        message = {"role": "assistant", "content": line}
        self.messages.append(message)
        logger.info(
            "turn_fast_path",
            call_log_id=self.call_log_id,
            stage=stage,
            next_stage=self.runtime.stage,
            saved=sorted(fields),
        )
        if close_after:
            self._closing = True
        self.speak(line, message_ref=message, allow_barge_in=not close_after, close_after=close_after)
        return True

    @staticmethod
    def _assistant_tool_message(reply: LLMReply) -> dict[str, Any]:
        if reply.assistant_message:
            return reply.assistant_message
        return {
            "role": "assistant",
            "content": reply.content or None,
            "tool_calls": [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
                for call in reply.tool_calls
            ],
        }

    async def _run_tool_call(self, call_id: str, name: str, raw_args: str) -> ToolResult:
        try:
            result = await self.tools.execute(name, raw_args, caller_text=self._last_user_text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("tool_execution_failed", call_log_id=self.call_log_id, tool_name=name, error=str(exc))
            result = ToolResult(
                payload={"ok": False, "error": "tool_failed", "instruction": "Briefly apologise and ask the customer to repeat their last answer."}
            )
        self.messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result.payload, ensure_ascii=False, default=str)})
        self._flush_directives()
        if result.say:
            self.messages.append({"role": "assistant", "content": result.say})
            if result.hang_up or result.transfer_to:
                self._closing = True
            self.speak(
                result.say,
                allow_barge_in=not (result.hang_up or result.transfer_to),
                close_after=bool(result.hang_up),
                transfer_to=result.transfer_to,
            )
        elif result.hang_up:
            self._closing = True
            self._schedule_hangup(None)
        return result

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
                if cache is not None and hasattr(tts, "cache_key"):
                    from app.voice.tts import voice_for

                    if cache.contains(tts.cache_key(text, voice=voice_for(self.persona, language))):
                        self.tts_cache_hits += 1
            except Exception:  # noqa: BLE001 — stats only
                pass
            self.tts_chars += len(text)
            try:
                return await tts.synthesize(text, language=language, persona=self.persona)
            except TTSError as exc:
                await logger.awarning("bridge_tts_failed", call_log_id=self.call_log_id, error=str(exc), preview=text[:80])
                return b""

    async def _play_utterance(self, utterance: _Utterance) -> None:
        sentences = speech_units(utterance.text)
        language = detect_language(utterance.text, supported=self.supported_languages) or self.active_language
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
        """Send μ-law to Twilio in paced 20 ms frames. Returns the fraction sent."""
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
            await self.websocket.send_json(
                {"event": "media", "streamSid": self.stream_sid, "media": {"payload": base64.b64encode(frame).decode("ascii")}}
            )
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
        self._twilio_mark_counter += 1
        mark_name = f"agent-{self._twilio_mark_counter}"
        self._pending_playback_mark = mark_name
        self._playback_mark_event.clear()
        await self.websocket.send_json({"event": "mark", "streamSid": self.stream_sid, "mark": {"name": mark_name}})
        timeout = max(0.5, self._playout_end - time.monotonic()) + 3.0
        try:
            await asyncio.wait_for(self._playback_mark_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if self._pending_playback_mark == mark_name:
                self._pending_playback_mark = None
                await logger.awarning("twilio_playback_mark_timeout", call_log_id=self.call_log_id, mark_name=mark_name)

    async def _interrupt_playback(self, reason: str) -> None:
        current = self._current_utterance
        if current is not None and not current.interrupted:
            current.interrupted = True
            if self.stream_sid and not self.closed:
                try:
                    await self.websocket.send_json({"event": "clear", "streamSid": self.stream_sid})
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

    def transcript_text(self) -> str:
        return "\n".join(f"{role}: {text}" for role, text in self.transcript_lines)

    async def _persist_transcript(self, *, force: bool = False) -> None:
        if not force and self._turn_counter - self._transcript_saved_turns < TRANSCRIPT_SAVE_EVERY:
            return
        if not self.transcript_lines:
            return
        self._transcript_saved_turns = self._turn_counter
        try:
            await self.store.save_transcript(self.transcript_text(), language=self.active_language, final_node=self.runtime.current_node)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("transcript_persist_failed", call_log_id=self.call_log_id, error=str(exc))

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
            if now - self.started_at >= self.max_call_seconds and not self._closing:
                await self._close_with_outcome(OUTCOME_UNCLEAR, timeout=True)
                return
            if self._closing:
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
        self._closing = True
        line = await self.tools.settle(outcome)
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
            await self._safe_close()

    async def _transfer_call(self, number: str) -> None:
        """Dial the merchant's support line once the transfer line has played."""
        await asyncio.sleep(0.3)
        try:
            ok = await self._dial_support(number)
        except Exception as exc:  # noqa: BLE001
            ok = False
            await logger.awarning("transfer_dial_failed", call_log_id=self.call_log_id, error=str(exc))
        if ok:
            await logger.ainfo("transfer_started", call_log_id=self.call_log_id, target=number)
            # Twilio ends the stream when the call moves to <Dial>; close our side too.
            await asyncio.sleep(2.0)
            await self._safe_close(end_twilio_call=False)
            return
        line = phrase("closing_transfer_callback", self.active_language)
        self.messages.append({"role": "assistant", "content": line})
        self.speak(line, allow_barge_in=False, close_after=True)

    async def _dial_support(self, number: str) -> bool:
        from app.services.call_service import redirect_call_to_human

        if not self.call_sid:
            return False
        return await redirect_call_to_human(self.call_sid, number)

    async def _end_twilio_call(self) -> None:
        if not self.call_sid:
            return
        from app.services.call_service import complete_call

        try:
            await complete_call(self.call_sid)
        except Exception as exc:  # noqa: BLE001
            await logger.ainfo("twilio_complete_call_failed", call_log_id=self.call_log_id, error=str(exc))

    async def _safe_close(self, *, code: int | None = None, end_twilio_call: bool = True) -> None:
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
        if end_twilio_call and not already_closed:
            await self._end_twilio_call()
