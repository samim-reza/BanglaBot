"""The transcriber failing mid-call: a dropped or broken STT socket is reconnected
(caller audio in the gap is kept and delivered), a session that served the call for a
while earns a fresh retry budget, and only a transcriber that cannot come back ends the
call — with the "can't hear you" goodbye, never a silent hang-up."""

from __future__ import annotations

import asyncio
import base64

from app.flows.base import OUTCOME_AUTO_DROPPED
from app.voice.languages import phrase
from app.voice.providers.base import ProviderUnavailable
from app.voice.providers.stt import health
from tests.bridge_fakes import ScriptedSTT, reply, wait_until
from tests.bridge_harness import build_call, fast_timing


def _frame(value: int) -> str:
    return base64.b64encode(bytes([value]) * 160).decode("ascii")


def _opener(plan: list):
    """``open_stt`` replacement: each call takes the next plan step (a session, an error,
    or an ``asyncio.Event`` to wait on first); the last step repeats."""

    async def open_stt(**kwargs):
        step = plan.pop(0) if len(plan) > 1 else plan[0]
        if isinstance(step, asyncio.Event):
            await step.wait()
        elif isinstance(step, BaseException):
            raise step
        stt = ScriptedSTT(**kwargs)
        await stt.connect()
        return stt

    return open_stt


async def test_dropped_stt_reconnects_and_keeps_what_the_caller_said_in_the_gap(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    gate = asyncio.Event()
    answer = "Of course. What time suits you?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], open_stt=_opener(["ok", gate, "ok"]), silence_seconds=30)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        first = call.stt
        first.drop()
        await wait_until(lambda: call.bridge._stt is None, what="session gone")
        gap = [_frame(0xF0 + i) for i in range(5)]
        for payload in gap:
            await call.ws.media(payload)
        gate.set()
        await wait_until(lambda: call.bridge._stt is not None and call.stt is not first, what="reconnected")
        await call.ws.media(_frame(0xFA))
        await wait_until(lambda: len(call.stt.audio) == 6, what="gap delivered")
        assert call.stt.audio == [*gap, _frame(0xFA)]  # in order, nothing lost
        await call.stt.says("can you deliver it in the afternoon")
        await wait_until(lambda: answer in call.agent_lines(), what="answer on the new session")
    assert first.closed and not call.ws.closed


async def test_broken_stt_stream_is_a_drop_not_the_end_of_the_call(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    answer = "Of course. What time suits you?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], silence_seconds=30)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        first = call.stt
        first.break_stream(ConnectionResetError("connection reset by peer"))
        await wait_until(lambda: call.stt is not first and call.bridge._stt is call.stt, what="reconnected")
        await call.stt.says("can you deliver it in the afternoon")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert len(call.bridge._stt_usage) >= 1  # the first session's usage was kept for billing


async def test_stt_that_cannot_come_back_ends_the_call_with_a_goodbye(monkeypatch, order, merchant):
    fast_timing(monkeypatch, STT_RETRY_SECONDS=0.01)
    plan = ["ok", ProviderUnavailable("no STT provider could serve 'en'")]
    call = build_call(monkeypatch, order, merchant, open_stt=_opener(plan), silence_seconds=30)
    async with call.running() as run_task:
        await wait_until(call.opening_done, what="opening")
        call.stt.drop()
        await asyncio.wait_for(run_task, timeout=5.0)
    assert call.agent_lines()[-1] == phrase("closing_dropped", "en")
    assert call.bridge.outcome == OUTCOME_AUTO_DROPPED and call.store.outcomes[-1]["status"] == "no_answer"
    assert call.ws.closed and call.bridge._closed_by_agent


async def test_initial_stt_failure_is_retried_after_the_greeting(monkeypatch, order, merchant):
    fast_timing(monkeypatch, STT_RETRY_SECONDS=0.01)
    answer = "Of course. What time suits you?"
    plan = [ProviderUnavailable("deepgram: connect timeout"), "ok"]
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], open_stt=_opener(plan), silence_seconds=30)
    async with call.running(wait_stt=False):
        await wait_until(lambda: call.bridge._stt is not None, what="connected on the retry")
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("can you deliver it in the afternoon")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")


async def test_reconnect_budget_resets_after_a_healthy_session(monkeypatch, order, merchant):
    fast_timing(monkeypatch, STT_HEALTHY_SECONDS=0.2)
    answer = "Of course. What time suits you?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], silence_seconds=30)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        for _ in range(5):  # more drops than STT_MAX_RECONNECTS, each after a healthy stretch
            await asyncio.sleep(0.25)
            current = call.stt
            current.drop()
            await wait_until(lambda: call.stt is not current and call.bridge._stt is call.stt, what="reconnected")
        assert not call.bridge.closed
        await call.stt.says("can you deliver it in the afternoon")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert len(ScriptedSTT.instances) == 6


async def test_stt_send_errors_do_not_end_the_call(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    answer = "Of course. What time suits you?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], silence_seconds=30)
    async with call.running():
        await wait_until(call.opening_done, what="opening")

        async def broken_send(payload: str) -> None:
            raise RuntimeError("socket is closing")

        monkeypatch.setattr(call.stt, "send_audio_b64", broken_send)
        await call.ws.media(_frame(0xF1), 10)
        await asyncio.sleep(0.05)
        assert not call.bridge.closed  # the media loop survived
        await call.stt.says("can you deliver it in the afternoon")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")


class _Session:
    def __init__(self, name: str) -> None:
        self.name = name
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False


async def test_a_paused_provider_is_still_tried_as_a_last_resort(monkeypatch):
    from app.voice.providers import stt as registry

    health.reset()
    monkeypatch.setattr(
        registry,
        "PROVIDERS",
        {name: registry.STTProvider(name, lambda: True, lambda lang, prompt, terms, name=name: _Session(name)) for name in ("deepgram", "groq")},
    )
    try:
        health.mark_down("deepgram", 60, reason="dropped mid-call")
        assert (await registry.open_stt(language="en", chain=["deepgram", "groq"])).name == "groq"  # healthy first
        assert (await registry.open_stt(language="en", chain=["deepgram"])).name == "deepgram"  # better than no call
    finally:
        health.reset()
