"""``CallBridge``: one call's transport state, assembled from the bridge mixins.

Each mixin owns one concern (see :mod:`app.voice.bridge`); this module holds the
constructor that sets up the shared state they all read, plus the agent views and
the per-call limits.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from fastapi import WebSocket

from app.core.config import get_settings
from app.core.regions import region_of
from app.flows.base import Flow
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext
from app.voice.agent import CallAgent
from app.voice.audio import AmbientNoiseTracker
from app.voice.bridge.hangup import HangupMixin
from app.voice.bridge.lifecycle import LifecycleMixin
from app.voice.bridge.media import PREROLL_FRAMES, STT_GAP_FRAMES, MediaMixin
from app.voice.bridge.speaker import SpeakerMixin
from app.voice.bridge.stt_loop import SttMixin
from app.voice.bridge.transcript import TranscriptMixin
from app.voice.bridge.turns import TurnsMixin
from app.voice.bridge.utterance import _Utterance
from app.voice.bridge.watchdog import WatchdogMixin
from app.voice.languages import normalize_supported
from app.voice.prompts import transcription_prompt
from app.voice.providers.base import LLMClient, STTSession
from app.voice.tools import CallStore
from app.voice.tts import normalize_persona, voice_for


class CallBridge(
    LifecycleMixin,
    MediaMixin,
    SttMixin,
    TurnsMixin,
    SpeakerMixin,
    TranscriptMixin,
    WatchdogMixin,
    HangupMixin,
):
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
        # The account's language is THE call language: no per-turn auto-detect.
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
            phone_call=not web,
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
        self._agent_handle_task: asyncio.Task[None] | None = None
        #: The text the agent is answering right now, and a cancelled turn's text (the caller
        #: kept talking) waiting to be answered together with what they said next.
        self._agent_turn_text = ""
        self._carry_text = ""
        #: STT says the caller is talking (speech_started / words since the last final), and when.
        self._caller_speech_open = False
        self._caller_active_at = 0.0
        #: Real replies queued (not acks / hold lines): a turn that queued none gets the recovery line.
        self._replies_queued = 0

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
        self._tts_silent_lines = 0
        #: What a barge-in cut off (utterance, unheard text) — resumed when no words follow.
        self._unheard: list[tuple[_Utterance, str]] = []
        self._unheard_at = 0.0
        self.tts_chars = 0
        self.tts_cache_hits = 0

        # --- audio in / barge-in ---
        self._ambient_noise = AmbientNoiseTracker()
        self._barge_in_window: deque[int] = deque(maxlen=max(2, self.settings.voice_barge_in_min_frames * 2))
        self._barge_in_loud_frames = 0
        # Caller frames held back while the agent speaks (not sent = not billed by a
        # streaming STT): the barge-in detection window plus a short pre-roll, so the
        # first syllable of a real interruption still reaches the transcriber.
        self._barge_in_prebuffer: deque[str] = deque(maxlen=(self._barge_in_window.maxlen or 0) + PREROLL_FRAMES)
        self._last_barge_in_at = 0.0
        self._stt_gap: deque[str] = deque(maxlen=STT_GAP_FRAMES)
        self._stt_send_failed = False
        self._stt_usage: list[dict[str, Any]] = []
        #: provider → {"chars": synthesised (billed), "cached_chars": served from cache} for this call.
        self._tts_usage: dict[str, dict[str, int]] = {}

        # --- watchdog / lifecycle ---
        self.started_at = time.monotonic()
        self.last_customer_audio_at = self.started_at
        self.last_voice_activity_at = self.started_at
        self._silence_counting_paused_until = 0.0
        self._last_busy_at = self.started_at
        self._silence_strikes = 0
        self._hangup_scheduled = False
        self._goodbye_hangup_delay_seconds = 8.0
        self._goodbye_playback_tail_seconds = 1.5
        self._closed_by_agent = False
        self._finalized = False

        # --- pipeline components (created in run) ---
        self._stt: STTSession | None = None
        self._llm: LLMClient | None = None

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
        """Idle seconds before the agent re-prompts (the account's setting, default 10)."""
        return max(3, int(getattr(self.merchant, "silence_hangup_secs", 0) or 10))

    @property
    def silence_reprompts(self) -> int:
        """Silent stretches answered with a re-prompt; the one after them drops the call."""
        return max(0, int(getattr(self.settings, "voice_silence_reprompts", 2)))


__all__ = ["CallBridge"]
