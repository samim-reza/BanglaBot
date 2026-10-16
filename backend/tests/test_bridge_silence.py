"""Caller silence on a live call: re-prompt with the unanswered question, then goodbye.

The silence clock must only run while the line is idle — never while the agent speaks,
while the model is thinking, or while the caller is mid-utterance — and only the
caller's words reset the strike count (a cough or a door is not an answer).
"""

from __future__ import annotations

import asyncio

import pytest

from app.flows.base import OUTCOME_AUTO_DROPPED
from app.voice.languages import phrase
from tests.bridge_fakes import LOUD_FRAME, FakeTTS, Slow, reply, seconds_of_audio, wait_until
from tests.bridge_harness import build_call, fast_timing, opening_line, is_reprompt, reprompt_line

SILENCE = 0.4


def _question(order) -> str:
    return phrase("opening_question", "en", customer_name=order.customer_name)


@pytest.mark.parametrize("reprompts", [None, 1, 3])
async def test_silent_caller_is_reprompted_then_dropped(monkeypatch, order, merchant, reprompts):
    fast_timing(monkeypatch)
    settings = {} if reprompts is None else {"voice_silence_reprompts": reprompts}
    call = build_call(monkeypatch, order, merchant, silence_seconds=SILENCE, settings=settings).track()
    expected = 2 if reprompts is None else reprompts  # the platform default is two re-prompts
    async with call.running() as run_task:
        await asyncio.wait_for(run_task, timeout=10.0)
    reprompts = [reprompt_line(_question(order), strike) for strike in range(1, expected + 1)]
    lines = [text for _, text in call.queued]
    assert lines == [opening_line(order), *reprompts, phrase("closing_dropped", "en")]
    assert call.agent_lines()[-1] == phrase("closing_dropped", "en")
    assert call.bridge.outcome == OUTCOME_AUTO_DROPPED and call.store.outcomes[-1]["status"] == "no_answer"
    assert call.ws.closed and call.bridge._closed_by_agent
    # Every silent stretch is measured from the end of the previous line, never shorter.
    ends = [t for t, _ in call.finished]
    starts = [t for t, _ in call.queued]
    assert all(start - end >= SILENCE - 0.01 for end, start in zip(ends, starts[1:]))
    # The model saw its re-prompts, so an answer to them is read in context.
    assistant = [m["content"] for m in call.bridge.messages if m["role"] == "assistant"]
    assert assistant[-expected:] == reprompts


async def test_caller_words_reset_the_count_and_the_reprompt_follows_the_new_question(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    question = "Which size would you like, medium or large?"
    call = build_call(monkeypatch, order, merchant, script=[reply(question)], silence_seconds=SILENCE)
    async with call.running() as run_task:
        await wait_until(lambda: reprompt_line(_question(order)) in call.agent_lines(), what="first re-prompt")
        await call.stt.says("I was in the other room, what is this about")
        await asyncio.wait_for(run_task, timeout=10.0)
    assert call.agent_lines() == [
        opening_line(order),
        reprompt_line(_question(order)),
        question,
        reprompt_line(question, 1),  # the strikes started over after the caller spoke
        reprompt_line(question, 2),
        phrase("closing_dropped", "en"),
    ]


async def test_noise_restarts_the_clock_but_does_not_reset_the_strikes(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, silence_seconds=SILENCE)
    async with call.running() as run_task:
        await wait_until(lambda: reprompt_line(_question(order)) in call.agent_lines(), what="first re-prompt")
        call.stt.push("speech_started")  # a cough: speech detected, no words
        call.stt.push("speech_stopped")
        await asyncio.wait_for(run_task, timeout=10.0)
    reprompts = [line for line in call.agent_lines() if is_reprompt(line)]
    assert len(reprompts) == 2 and call.agent_lines()[-1] == phrase("closing_dropped", "en")


async def test_no_silence_counted_while_the_agent_speaks_a_long_line(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    long_answer = "We are open every day from nine to six, and on Sundays from ten to four. Anything else?"
    tts = FakeTTS(audio_for=lambda text: seconds_of_audio(1.5) if text == long_answer else None)
    call = build_call(monkeypatch, order, merchant, script=[reply(long_answer)], tts=tts, silence_seconds=SILENCE).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("what are your opening hours on the weekend")
        await wait_until(lambda: long_answer in call.agent_lines(), timeout=6.0, what="long answer played")
        answer_queued = next(t for t, text in call.queued if text == long_answer)
        answer_done = next(t for t, text in call.finished if text == long_answer)
        assert answer_done - answer_queued >= 1.0  # the line really played for longer than the silence window
        assert call.bridge._silence_strikes == 0 and not any(is_reprompt(text) for _, text in call.queued)
        await wait_until(lambda: call.agent_lines()[-1] == reprompt_line("Anything else?"), timeout=3.0, what="re-prompt after it")
        reprompt_at = next(t for t, text in call.queued if text == reprompt_line("Anything else?"))
        assert reprompt_at - answer_done >= SILENCE


async def test_no_silence_counted_while_the_model_is_thinking(monkeypatch, order, merchant):
    fast_timing(monkeypatch, HOLD_LINE_SECONDS=10.0)
    answer = "Let me see. Your parcel leaves the warehouse tomorrow. Shall I text you the tracking link?"
    call = build_call(monkeypatch, order, merchant, script=[Slow(1.3, reply(answer))], silence_seconds=SILENCE).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says("when will my parcel arrive at the house")
        await wait_until(lambda: answer in call.agent_lines(), timeout=5.0, what="slow answer")
        # 1.3 s of thinking > the 0.4 s silence window, yet no re-prompt while the caller waited.
        assert [text for _, text in call.queued] == [opening_line(order), answer]


async def test_no_silence_counted_while_the_caller_is_mid_utterance(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    answer = "Sure, I can change that. What is the new address?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], silence_seconds=SILENCE).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        # A slow, quiet speaker: interim words keep coming for 1.6 s before the final.
        call.stt.push("speech_started")
        words = "I would like to have the parcel delivered to my office on Baker Street instead".split()
        for size in range(2, len(words) + 1, 2):
            call.stt.push("delta", " ".join(words[:size]))
            await asyncio.sleep(0.2)
        assert [text for _, text in call.queued] == [opening_line(order)]  # no re-prompt mid-sentence
        call.stt.push("speech_stopped")
        call.stt.push("completed", " ".join(words))
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
        assert call.customer_lines() == [" ".join(words)]


async def test_caller_audio_keeps_the_clock_from_running(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, silence_seconds=SILENCE).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.ws.media(LOUD_FRAME, 50, pace=0.02)  # a second of audible caller audio, no transcript yet
        assert [text for _, text in call.queued] == [opening_line(order)]
        await wait_until(lambda: len(call.queued) == 2, timeout=3.0, what="re-prompt once the line went quiet")
        assert call.queued[1][1] == reprompt_line(_question(order))
