"""Never silent: every completed caller turn ends in agent speech — through model
errors, empty replies, slow or hung models, stuck tools and failing TTS providers —
and a call whose voice is gone entirely is ended instead of left in dead air."""

from __future__ import annotations

import asyncio

from app.flows.base import OUTCOME_AUTO_DROPPED
from app.voice.languages import phrase
from app.voice.llm import LLMError
from app.voice.providers.tts.base import CachedTTSEngine, TTSError
from app.voice.providers.tts.fallback import FallbackTTS
from app.voice.tools import ToolResult
from app.voice.tts_cache import TTSCache
from app.voice.tts_tiers import TieredTTSCache
from tests.bridge_fakes import HANG, FakeTTS, Slow, reply, tool, wait_until
from tests.bridge_harness import build_call, fast_timing, opening_line

RECOVERY = phrase("recovery", "en")
HOLD = phrase("working", "en")


def _valid_tool_pairs(messages) -> bool:
    """Every assistant tool call is answered by a tool message (Chat Completions' rule)."""
    for index, message in enumerate(messages):
        for call in message.get("tool_calls") or []:
            if not any(m.get("role") == "tool" and m.get("tool_call_id") == call["id"] for m in messages[index + 1 :]):
                return False
    return True


async def test_model_failure_gets_the_recovery_line_and_the_call_goes_on(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    answer = "Sure. Which day works best for the delivery?"
    call = build_call(monkeypatch, order, merchant, script=[LLMError("all LLM providers failed"), reply(answer)], silence_seconds=30)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("can the parcel come a little earlier this week")
        await wait_until(lambda: RECOVERY in call.agent_lines(), what="recovery line")
        await call.stt.says("can the parcel come earlier this week please")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert call.agent_lines() == [opening_line(order), RECOVERY, answer]


async def test_empty_model_reply_asks_the_current_question_again(monkeypatch, order, merchant):
    # An empty model reply is never silence — and not "something went wrong" either: the step's question again.
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, script=[reply("")], silence_seconds=30)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        before = len(call.agent_lines())
        await call.stt.says("can the parcel come a little earlier this week")
        await wait_until(lambda: len(call.agent_lines()) > before, what="a re-ask")
    instruction = call.bridge.runtime.current_instruction()
    expected = instruction.text if instruction.verbatim and not instruction.end_call else phrase("unclear_2", "en")
    assert call.bridge.messages[-1] == {"role": "assistant", "content": expected} and expected != RECOVERY


async def test_slow_model_gets_a_hold_line_then_the_answer(monkeypatch, order, merchant):
    fast_timing(monkeypatch, HOLD_LINE_SECONDS=0.3)
    answer = "Thanks for waiting. The parcel can come on Thursday. Shall I arrange that?"
    call = build_call(monkeypatch, order, merchant, script=[Slow(0.9, reply(answer))], silence_seconds=30).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("can the parcel come a little earlier this week")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert [text for _, text in call.queued] == [opening_line(order), HOLD, answer]
    assert all(m.get("content") != HOLD for m in call.bridge.messages)  # filler, not history


async def test_hung_model_is_abandoned_at_the_deadline(monkeypatch, order, merchant):
    fast_timing(monkeypatch, HOLD_LINE_SECONDS=0.2, TURN_DEADLINE_SECONDS=0.6)
    answer = "Sorry about that. Thursday works. Shall I book it?"
    call = build_call(monkeypatch, order, merchant, script=[HANG, reply(answer)], silence_seconds=30).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("can the parcel come a little earlier this week")
        await wait_until(lambda: RECOVERY in call.agent_lines(), timeout=3.0, what="recovery after the deadline")
        assert call.llm.cancelled == 1
        await call.stt.says("I asked whether it can come earlier this week")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert [text for _, text in call.queued] == [opening_line(order), HOLD, RECOVERY, answer]
    # The abandoned turn left no half-written history behind.
    assert call.llm.user_messages(1) == ["I asked whether it can come earlier this week"]


async def test_stuck_tool_is_abandoned_without_breaking_the_history(monkeypatch, order, merchant):
    fast_timing(monkeypatch, HOLD_LINE_SECONDS=5.0, TURN_DEADLINE_SECONDS=0.5)
    answer = "Thanks. Which address should we use instead?"
    script = [reply(tool_calls=[tool("c1", "save_details", '{"notes": "deliver to office"}')]), reply(answer)]
    call = build_call(monkeypatch, order, merchant, script=script, silence_seconds=30)
    tools = call.bridge.agent.tools
    original = tools.execute
    stuck = {"first": True}

    async def execute(name, raw_args, caller_text=""):
        if stuck.pop("first", False):
            await asyncio.Event().wait()  # a database call that never returns
        return await original(name, raw_args, caller_text=caller_text)

    monkeypatch.setattr(tools, "execute", execute)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("please deliver the parcel to my office address")
        await wait_until(lambda: RECOVERY in call.agent_lines(), timeout=3.0, what="recovery after the deadline")
        assert _valid_tool_pairs(call.bridge.messages)
        await call.stt.says("the office on Baker Street please")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert _valid_tool_pairs(call.llm.calls[1])


async def test_turn_that_ends_without_a_line_gets_the_recovery_line(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    script = [reply(tool_calls=[tool("c1", "save_details", "{}")])]
    call = build_call(monkeypatch, order, merchant, script=script, silence_seconds=30)

    async def silent_stop(name, raw_args, caller_text=""):
        return ToolResult(payload={"ok": True, "instruction": "Say nothing."}, stop=True)

    monkeypatch.setattr(call.bridge.agent.tools, "execute", silent_stop)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("please deliver the parcel to my office address")
        await wait_until(lambda: RECOVERY in call.agent_lines(), what="recovery line")


class _Engine(CachedTTSEngine):
    def __init__(self, name: str, cache: TieredTTSCache, *, mode: str = "ok") -> None:
        super().__init__(cache=cache)
        self.name = name
        self.mode = mode
        self.calls = 0

    def resolve_voice(self, *, voice, persona, language):
        return f"{self.name}-{persona or 'female'}"

    async def render(self, text, *, voice, language):
        self.calls += 1
        if self.mode == "hang":
            await asyncio.Event().wait()
        if self.mode == "fail":
            raise TTSError(f"{self.name} down")
        return b"\x20" * 800


async def test_tts_provider_that_hangs_or_fails_hands_over_to_the_next(monkeypatch, order, merchant, tmp_path):
    fast_timing(monkeypatch)
    cache = TieredTTSCache(TTSCache(tmp_path))
    hanging, failing, working = _Engine("hanging", cache, mode="hang"), _Engine("failing", cache, mode="fail"), _Engine("working", cache)
    chain = FallbackTTS([hanging, failing, working], cache=cache, attempt_timeout=0.2)
    answer = "Sure, Thursday it is. Anything else I can help with?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], tts=chain, silence_seconds=30)
    async with call.running():
        await wait_until(lambda: call.agent_lines() == [opening_line(order)], timeout=3.0, what="opening via the fallback")
        await call.stt.says("can the parcel come on thursday instead")
        await wait_until(lambda: answer in call.agent_lines(), timeout=3.0, what="answer via the fallback")
    assert set(call.bridge._tts_usage) == {"working"} and working.calls >= 2
    assert chain.is_open("hanging") or chain.is_open("failing")


async def test_voice_gone_entirely_ends_the_call_instead_of_dead_air(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    opening = opening_line(order)
    tts = FakeTTS(fail=lambda text: text != opening)  # only the cached greeting still plays
    call = build_call(monkeypatch, order, merchant, default=lambda: reply("Sure, let me look into that for you."), tts=tts, silence_seconds=30)
    async with call.running() as run_task:
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("can the parcel come a little earlier this week")
        await wait_until(lambda: call.bridge._tts_silent_lines == 1, what="first silent reply")
        assert not call.ws.closed
        await call.stt.says("hello can you hear me at all")
        await asyncio.wait_for(run_task, timeout=5.0)
    assert call.ws.closed and call.bridge._closed_by_agent
    assert call.bridge.outcome == OUTCOME_AUTO_DROPPED and call.store.outcomes[-1]["status"] == "no_answer"


async def test_failed_settle_still_says_goodbye_and_hangs_up(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, silence_seconds=0.3, settings={"voice_silence_reprompts": 0})

    async def broken_settle(outcome):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(call.bridge.agent, "settle", broken_settle)
    async with call.running() as run_task:
        await asyncio.wait_for(run_task, timeout=5.0)
    assert call.agent_lines()[-1] == phrase("closing_dropped", "en") and call.ws.closed
