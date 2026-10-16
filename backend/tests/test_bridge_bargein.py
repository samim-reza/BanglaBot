"""Barge-in: a caller who really talks over the agent stops it and is heard; a cough,
steady background noise or the agent's own echo does not cut it off; protected lines
(greeting, goodbye) always finish; and a loud noise that did cut a line off (no words
followed) lets the agent finish what it was saying instead of leaving dead air."""

from __future__ import annotations

import asyncio
import base64

from app.voice.codec import linear_to_ulaw
from tests.bridge_fakes import LOUD_FRAME, SILENT_FRAME, FakeTTS, reply, seconds_of_audio, wait_until
from tests.bridge_harness import build_call, fast_timing, opening_line

LINE = "Your parcel ships tomorrow morning from our warehouse. Would you like a text message when it leaves?"
# Steady noise well above the speech gate but under the barge-in gate (1100 RMS).
HUM_FRAME = base64.b64encode(bytes([linear_to_ulaw(700)]) * 160).decode("ascii")


def _long_tts(*lines: str) -> FakeTTS:
    return FakeTTS(audio_for=lambda text: seconds_of_audio(2.5) if text in lines else None)


async def _start_line(call, text: str) -> None:
    await wait_until(call.opening_done, what="opening")
    call.bridge.speak(text)
    await wait_until(lambda: call.bridge.assistant_speaking and call.bridge._current_utterance.text == text, what="line playing")
    await asyncio.sleep(0.3)


async def test_caller_talking_over_the_agent_stops_it_and_is_heard(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    follow_up = "And would you like it left with a neighbour?"
    call = build_call(monkeypatch, order, merchant, tts=_long_tts(LINE), silence_seconds=30)
    async with call.running():
        await _start_line(call, LINE)
        message = {"role": "assistant", "content": follow_up}
        call.bridge.speak(follow_up, message_ref=message)  # queued behind the line
        await call.ws.media(LOUD_FRAME, 25)
        await wait_until(lambda: call.ws.clears() >= 1 and not call.bridge.assistant_speaking, what="cut off")
        await asyncio.sleep(0.1)
        clear_at = next(i for i, m in enumerate(call.ws.sent) if m.get("event") == "clear")
        assert sum(1 for m in call.ws.sent[clear_at:] if m.get("event") == "media") <= 1  # playback stopped at once
        assert len(call.stt.audio) >= 20  # the start of the interruption reached the transcriber
        assert message["content"] == "(interrupted before speaking)"  # the model won't think it was heard
        assert follow_up not in call.agent_lines()


async def test_a_cough_does_not_cut_the_agent_off(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, tts=_long_tts(LINE), silence_seconds=30)
    async with call.running():
        await _start_line(call, LINE)
        await call.ws.media(LOUD_FRAME, 8)  # ~160 ms burst: below the sustained-speech threshold
        await call.ws.media(SILENT_FRAME, 10)
        await wait_until(lambda: LINE in call.agent_lines(), timeout=4.0, what="line finished")
    assert call.ws.clears() == 0


async def test_steady_background_noise_does_not_cut_the_agent_off(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, tts=_long_tts(LINE), silence_seconds=30)
    async with call.running():
        await _start_line(call, LINE)
        await call.ws.media(HUM_FRAME, 80, pace=0.005)
        await wait_until(lambda: LINE in call.agent_lines(), timeout=4.0, what="line finished")
        assert call.stt.audio == []  # half duplex: noise while the agent talks is never sent (or billed)
    assert call.ws.clears() == 0


async def test_greeting_is_protected_from_barge_in(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, tts=_long_tts(opening_line(order)), silence_seconds=30)
    async with call.running():
        await wait_until(lambda: call.bridge.assistant_speaking, what="greeting playing")
        await call.ws.media(LOUD_FRAME, 40)
        await wait_until(lambda: call.agent_lines() == [opening_line(order)], timeout=4.0, what="greeting finished")
    assert call.ws.clears() == 0


async def test_noise_that_cut_a_line_off_lets_the_agent_finish_it(monkeypatch, order, merchant):
    fast_timing(monkeypatch, FALSE_BARGE_IN_SECONDS=0.4)
    call = build_call(monkeypatch, order, merchant, tts=_long_tts(LINE), silence_seconds=30).track()
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        message = {"role": "assistant", "content": LINE}
        call.bridge.speak(LINE, message_ref=message)
        await wait_until(lambda: call.bridge.assistant_speaking and call.bridge._current_utterance.text == LINE, what="line playing")
        await asyncio.sleep(0.3)
        await call.ws.media(LOUD_FRAME, 25)  # a door slam: loud and sustained, but no words follow
        await wait_until(lambda: call.ws.clears() >= 1, what="cut off")
        await wait_until(lambda: len(call.queued) == 3, timeout=3.0, what="line resumed")
    resumed = call.queued[2][1]
    assert LINE.endswith(resumed) and resumed in (LINE, "Would you like a text message when it leaves?")
    assert message["content"] == LINE  # the caller did hear all of it in the end


async def test_words_after_a_barge_in_win_over_resuming(monkeypatch, order, merchant):
    fast_timing(monkeypatch, FALSE_BARGE_IN_SECONDS=0.4)
    answer = "No problem, I will leave it with your neighbour."
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], tts=_long_tts(LINE), silence_seconds=30).track()
    async with call.running():
        await _start_line(call, LINE)
        await call.ws.media(LOUD_FRAME, 25)
        await wait_until(lambda: call.ws.clears() >= 1, what="cut off")
        await call.stt.says("just leave it next door with my neighbour")
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
        await asyncio.sleep(0.6)
    assert [text for _, text in call.queued][-1] == answer  # nothing resumed after the caller spoke
