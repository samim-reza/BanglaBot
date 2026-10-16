"""The end of a call: the time limit wraps up with a goodbye (a reply still being thought
out never plays after it), a goodbye that hangs is cut by a hard stop, and every hang-up
ends the phone leg BEFORE the media socket closes (Telnyx re-opens a dropped stream on a
live call, which would start the conversation over)."""

from __future__ import annotations

import asyncio
import time

from app.flows.base import OUTCOME_UNCLEAR
from app.services import call_service
from app.voice import prepared
from app.voice.bridge import CallBridge
from app.voice.languages import phrase
from tests.bridge_fakes import FakeTTS, Slow, reply, tool, wait_until
from tests.bridge_harness import build_call, fast_timing

TIMEOUT_LINE = phrase("closing_timeout", "en")


def _phone_leg(monkeypatch, call) -> list[float]:
    """Telnyx call control replaced: ``complete_call`` is logged in the socket's order log."""
    hung_up: list[float] = []

    async def complete_call(call_sid: str) -> None:
        hung_up.append(time.monotonic())
        call.ws.log.append("phone")

    monkeypatch.setattr(call_service, "complete_call", complete_call)
    return hung_up


async def test_time_limit_says_goodbye_drops_the_late_reply_and_hangs_up_phone_first(monkeypatch, order, merchant):
    fast_timing(monkeypatch, HOLD_LINE_SECONDS=10.0)
    monkeypatch.setattr(CallBridge, "max_call_seconds", property(lambda self: 1))
    late = "Here is everything about your parcel."
    call = build_call(monkeypatch, order, merchant, script=[Slow(1.5, reply(late))], call_sid="v3:call-limit", silence_seconds=30).track()
    hung_up = _phone_leg(monkeypatch, call)
    prepared.clear()
    async with call.running() as run_task:
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("tell me everything about where my parcel is right now")
        await asyncio.wait_for(run_task, timeout=6.0)
    queued = [text for _, text in call.queued]
    assert queued[-1] == TIMEOUT_LINE and late not in queued  # the reply that arrived after the goodbye was dropped
    assert call.bridge.outcome == OUTCOME_UNCLEAR and call.store.outcomes[-1]["status"] == "needs_review"
    assert call.ws.log == ["phone", "socket"]
    goodbye_done = next(t for t, text in call.finished if text == TIMEOUT_LINE)
    assert hung_up and hung_up[0] >= goodbye_done  # the caller heard the whole goodbye
    assert prepared.call_ended(call.bridge.call_log_id)  # a re-opened stream will not restart the call
    prepared.clear()


async def test_a_goodbye_that_never_finishes_is_cut_by_the_hard_stop(monkeypatch, order, merchant):
    fast_timing(monkeypatch, HARD_STOP_GRACE_SECONDS=0.5)
    monkeypatch.setattr(CallBridge, "max_call_seconds", property(lambda self: 1))
    tts = FakeTTS(hang=lambda text: text == TIMEOUT_LINE)  # the goodbye's synthesis never returns
    call = build_call(monkeypatch, order, merchant, tts=tts, call_sid="v3:call-stuck", silence_seconds=30)
    _phone_leg(monkeypatch, call)
    started = time.monotonic()
    async with call.running() as run_task:
        await asyncio.wait_for(run_task, timeout=5.0)
    assert call.ws.log == ["phone", "socket"] and time.monotonic() - started < 3.0


async def test_agent_goodbye_hangs_up_after_it_has_played(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    script = [reply(tool_calls=[tool("c1", "end_call", '{"reason": "caller is done"}')])]
    call = build_call(monkeypatch, order, merchant, script=script, call_sid="v3:call-bye", silence_seconds=30).track()
    hung_up = _phone_leg(monkeypatch, call)
    async with call.running() as run_task:
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("I have to go now, thank you very much")
        await asyncio.wait_for(run_task, timeout=6.0)
    goodbye_at, goodbye = call.finished[-1]
    assert goodbye != call.agent_lines()[0] and hung_up and hung_up[0] >= goodbye_at
    assert call.ws.log == ["phone", "socket"] and call.bridge._closed_by_agent


def test_call_limits_come_from_the_account_or_the_platform(order, merchant):
    from app.voice.tools import NullCallStore
    from tests.bridge_fakes import TelnyxSocket

    bridge = CallBridge(TelnyxSocket(), order=order, merchant=merchant, call_log_id="log-limits", stream_sid="st-1", store=NullCallStore())  # type: ignore[arg-type]
    assert bridge.max_call_seconds == bridge.settings.voice_max_call_seconds  # outbound default
    merchant.max_call_seconds = 180
    assert bridge.max_call_seconds == 180
    assert bridge.silence_seconds == 10 and bridge.silence_reprompts == 2
    merchant.silence_hangup_secs = 0
    assert bridge.silence_seconds == 10  # unset → the 10 s default
