"""Wires the fakes of :mod:`tests.bridge_fakes` into a real ``CallBridge``.

``build_call`` patches every external edge (STT chain, LLM factory, TTS chain, Jev, the
FAQ cache's Redis tier) and returns a ``Call`` to drive. Time is real but scaled down:
``fast_timing`` shrinks the bridge's timing constants (watchdog tick, silence pauses,
merge / hold windows, deadlines) for one test.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.pipeline import faq_cache
from app.voice import jev
from app.voice.bridge import CallBridge
from app.voice.bridge import lifecycle as bridge_lifecycle
from app.voice.bridge import speaker as bridge_speaker
from app.voice.bridge import stt_loop as bridge_stt
from app.voice.bridge import turns as bridge_turns
from app.voice.bridge import watchdog as bridge_watchdog
from app.voice.languages import phrase
from app.voice.tools import NullCallStore
from tests.bridge_fakes import FakeTTS, ScriptedLLM, ScriptedSTT, TelnyxSocket, wait_until

_call_ids = itertools.count(1)


@dataclass
class Call:
    bridge: CallBridge
    ws: TelnyxSocket
    tts: Any
    store: NullCallStore
    llm_holder: dict[str, ScriptedLLM] = field(default_factory=dict)

    @property
    def stt(self) -> ScriptedSTT:
        return ScriptedSTT.instances[-1]

    @property
    def llm(self) -> ScriptedLLM:
        return self.llm_holder["llm"]

    def agent_lines(self) -> list[str]:
        return [text for role, text in self.bridge.transcript_lines if role == "Agent"]

    def customer_lines(self) -> list[str]:
        return [text for role, text in self.bridge.transcript_lines if role == "Customer"]

    def opening_done(self) -> bool:
        return len(self.agent_lines()) >= 1 and not self.bridge.assistant_speaking and self.bridge._speech_queue.empty()

    def track(self) -> "Call":
        """Record when each line was queued (``queued``) and finished playing (``finished``)."""
        self.queued: list[tuple[float, str]] = []
        self.finished: list[tuple[float, str]] = []
        bridge = self.bridge
        speak, record = bridge.speak, bridge._record_assistant_transcript

        def tracked_speak(text: str, **kwargs: Any):
            utterance = speak(text, **kwargs)
            if utterance is not None:
                self.queued.append((time.monotonic(), utterance.text))
            return utterance

        def tracked_record(text: str) -> None:
            self.finished.append((time.monotonic(), text))
            record(text)

        bridge.speak = tracked_speak  # type: ignore[method-assign]
        bridge._record_assistant_transcript = tracked_record  # type: ignore[method-assign]
        return self

    @asynccontextmanager
    async def running(self, *, wait_stt: bool = True):
        task = asyncio.create_task(self.bridge.run())
        try:
            if wait_stt:
                await wait_until(lambda: self.bridge._stt is not None or task.done(), what="stt connected")
            yield task
        finally:
            if not task.done():
                task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


def fast_timing(monkeypatch: pytest.MonkeyPatch, **overrides: float) -> None:
    """Scale the bridge's clocks down for a test (any module constant can be overridden by name)."""
    knobs = {"WATCHDOG_TICK_SECONDS": 0.05, "QUEUED_LINE_SILENCE_PAUSE_SECONDS": 0.1, "TURN_MERGE_SECONDS": 0.15, "CALLER_ACTIVE_SECONDS": 0.5}
    modules = (bridge_watchdog, bridge_speaker, bridge_turns, bridge_stt)
    for name, value in {**knobs, **overrides}.items():
        module = next(m for m in modules if name.isupper() and hasattr(m, name))
        monkeypatch.setattr(module, name, value)


def build_call(
    monkeypatch: pytest.MonkeyPatch,
    order: Any,
    merchant: Any,
    *,
    script: list[Any] | None = None,
    default: Callable[[], Any] | None = None,
    tts: Any = None,
    open_stt: Callable[..., Any] | None = None,
    call_sid: str = "",
    silence_seconds: float | None = None,
    settings: dict[str, Any] | None = None,
) -> Call:
    ws = TelnyxSocket()
    tts = tts or FakeTTS()
    store = NullCallStore()
    llm_holder: dict[str, ScriptedLLM] = {}
    ScriptedSTT.instances.clear()

    def llm_factory(**kwargs: Any) -> ScriptedLLM:
        llm_holder["llm"] = ScriptedLLM(script or [], default=default, **kwargs)
        return llm_holder["llm"]

    async def scripted_open_stt(**kwargs: Any) -> ScriptedSTT:
        stt = ScriptedSTT(**kwargs)
        await stt.connect()
        return stt

    async def no_redis_get(key: str) -> str:
        return ""

    async def no_redis_set(key: str, answer: str) -> None:
        return None

    # Nothing leaves the process: no Jev requests, no Redis tier behind the FAQ cache.
    monkeypatch.setattr(jev, "enabled", lambda language="en": False)
    monkeypatch.setattr(faq_cache, "_redis_get", no_redis_get)
    monkeypatch.setattr(faq_cache, "_redis_set", no_redis_set)
    monkeypatch.setattr(bridge_stt, "open_stt", open_stt or scripted_open_stt)
    monkeypatch.setattr(bridge_lifecycle, "stt_available", lambda language=None: True)
    monkeypatch.setattr(bridge_lifecycle, "llm_for_call", llm_factory)
    monkeypatch.setattr(bridge_lifecycle, "llm_configured", lambda merchant=None: True)
    monkeypatch.setattr(bridge_speaker, "get_tts_for", lambda language=None, chain=None: tts)
    monkeypatch.setattr(bridge_lifecycle, "tts_available", lambda language=None: True)
    if silence_seconds is not None:
        monkeypatch.setattr(CallBridge, "silence_seconds", property(lambda self: silence_seconds))
    bridge = CallBridge(
        ws,  # type: ignore[arg-type]
        order=order,
        merchant=merchant,
        call_log_id=f"log-bridge-{next(_call_ids)}",
        stream_sid="st-1",
        call_sid=call_sid,  # empty → no Telnyx call control (no network)
        store=store,
    )
    bridge.settings = bridge.settings.model_copy(
        update={"openai_api_key": "sk-test", "azure_speech_key": "azure-test", "voice_instant_ack": False, **(settings or {})}
    )
    bridge._goodbye_playback_tail_seconds = 0.05
    return Call(bridge=bridge, ws=ws, tts=tts, store=store, llm_holder=llm_holder)


def opening_line(order: Any) -> str:
    return f"{phrase('greeting', 'en', business_name='Demo Shop')} {phrase('opening_question', 'en', customer_name=order.customer_name)}"


def reprompt_line(question: str, strike: int = 1) -> str:
    ask = phrase("still_there" if strike <= 1 else "still_there_again", "en")
    return f"{ask} {question}".strip()


def is_reprompt(line: str) -> bool:
    return line.startswith((phrase("still_there", "en"), phrase("still_there_again", "en")))
