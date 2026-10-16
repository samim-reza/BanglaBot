"""A caller who talks for a long time: a 400+ word monologue arriving as many STT finals
with short pauses must reach the model as ONE turn, whole, and be answered once —
the agent never answers a fragment and talks over the caller."""

from __future__ import annotations

import asyncio

import pytest

from app.voice.bridge.turns import clip_turn
from app.voice.languages import phrase
from tests.bridge_fakes import LOUD_FRAME, FakeTTS, ScriptedLLM, Slow, reply, seconds_of_audio, wait_until
from tests.bridge_harness import build_call, fast_timing

# Neutral words (no yes / no / repeat / identity cues) so the turn goes to the model.
_POOL = (
    "the kitchen tap started dripping last tuesday evening and water pooled under the cabinet near our dishwasher "
    "while a neighbour helped move boxes from the garage into the hallway because the plumber we used before moved "
    "to another town across the river so we searched online for someone local who could visit before the weekend "
    "and bring replacement washers pipes valves sealant tools ladders buckets towels gloves torches spare parts "
    "receipts invoices photos notes measurements for the basement boiler radiator thermostat upstairs bathroom "
    "shower drain which also gurgles every morning around seven when the children wake up for school breakfast "
    "toast coffee juice cereal fruit eggs pancakes honey butter marmalade kettle stove oven microwave fridge freezer "
    "pantry shelves cupboard drawers cutlery plates bowls glasses mugs napkins tablecloth chairs bench window "
    "curtains blinds garden fence gate path driveway bicycle scooter helmet jacket umbrella boots raincoat scarf"
).split()


def monologue(segments: int = 12, words: int = 35) -> list[str]:
    return [" ".join(_POOL[(i * words + k) % len(_POOL)] for k in range(words)) for i in range(segments)]


async def _speak_monologue(call, segments: list[str], pauses: list[float]) -> None:
    for index, segment in enumerate(segments):
        await call.stt.says(segment)
        if index < len(segments) - 1:
            await asyncio.sleep(pauses[index % len(pauses)])


@pytest.mark.parametrize("instant_ack", [False, True])
async def test_monologue_with_pauses_reaches_the_model_whole_and_is_answered_once(monkeypatch, order, merchant, instant_ack):
    fast_timing(monkeypatch, HOLD_LINE_SECONDS=10.0)
    answer = "Thank you for all the detail. A plumber can come on Saturday morning. Does that suit you?"
    call = build_call(
        monkeypatch, order, merchant, default=lambda: Slow(0.8, reply(answer)), silence_seconds=30, settings={"voice_instant_ack": instant_ack}
    ).track()
    segments = monologue()
    full = " ".join(segments)
    assert len(full.split()) >= 400
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        # Pauses both shorter and longer than the merge window: the longer ones start a reply
        # that the caller's next words cancel while the model is still thinking.
        await _speak_monologue(call, segments, [0.05, 0.3, 0.1, 0.4, 0.2])
        await wait_until(lambda: answer in call.agent_lines(), timeout=6.0, what="the one answer")
        await asyncio.sleep(0.3)
    llm = call.llm
    assert llm.user_messages()[-1] == full  # every word, in order, in one user message
    assert llm.cancelled == len(llm.calls) - 1  # replies to fragments were dropped, not spoken
    replies = [text for _, text in call.queued[1:]]
    assert replies == ([phrase("ack", "en")] if instant_ack else []) + [answer]  # one ack at most, one answer
    assert [m["content"] for m in call.bridge.messages if m["role"] == "user"] == [full]  # no fragments left behind
    assert call.bridge.agent.turns == 1
    assert " ".join(call.customer_lines()) == full


async def test_turn_is_held_open_while_the_caller_is_still_talking(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    answer = "Got all of that. Shall I send someone tomorrow?"
    call = build_call(monkeypatch, order, merchant, script=[reply(answer)], silence_seconds=30)
    first, second = monologue(2, 20)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says(first)
        await asyncio.sleep(0.05)
        call.stt.push("speech_started")  # resumes within the merge window and keeps going for 0.8 s
        words = second.split()
        for size in range(4, len(words), 4):
            call.stt.push("delta", " ".join(words[:size]))
            await asyncio.sleep(0.2)
        assert call.llm_holder["llm"].calls == []  # nothing was sent to the model mid-sentence
        call.stt.push("speech_stopped")
        call.stt.push("completed", second)
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
    assert call.llm.calls and call.llm.user_messages(0)[-1] == f"{first} {second}" and call.llm.cancelled == 0


async def test_caller_who_keeps_talking_over_the_reply_interrupts_it_and_is_answered(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    first_answer = "I see, a leaking tap. Is the water still running right now, or did you close the valve?"
    second_answer = "Understood, thank you. I will book a visit for tomorrow morning."
    tts = FakeTTS(audio_for=lambda text: seconds_of_audio(2.0) if text == first_answer else None)
    call = build_call(monkeypatch, order, merchant, script=[reply(first_answer), reply(second_answer)], tts=tts, silence_seconds=30)
    first, second = monologue(2, 20)
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says(first)
        await wait_until(lambda: call.bridge.assistant_speaking and call.bridge._current_utterance.text == first_answer, what="reply playing")
        await call.ws.media(LOUD_FRAME, 25)  # the caller talks over it: a real barge-in
        await wait_until(lambda: call.ws.clears() >= 1 and not call.bridge.assistant_speaking, what="reply cut off")
        await call.stt.says(second)
        await wait_until(lambda: second_answer in call.agent_lines(), what="second answer")
    later = call.llm.calls[1]
    users = [m["content"] for m in later if m["role"] == "user"]
    assert users[-2:] == [first, second]
    interrupted = [m for m in later if m["role"] == "assistant"][-1]
    assert interrupted["content"] != first_answer  # the model knows its reply was cut short


async def test_very_long_turn_keeps_its_beginning_and_end(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    monkeypatch.setattr("app.voice.bridge.turns.MAX_TURN_CHARS", 600)
    call = build_call(monkeypatch, order, merchant, script=[reply("Thanks, noted.")], silence_seconds=30)
    text = " ".join(monologue(6, 30))
    assert len(text) > 1000
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says(text)
        await wait_until(lambda: "Thanks, noted." in call.agent_lines(), what="answer")
    sent = call.llm.user_messages(0)[-1]
    assert len(sent) <= 600 and "…" in sent
    assert sent.startswith(" ".join(text.split()[:10])) and sent.endswith(" ".join(text.split()[-10:]))
    assert call.customer_lines() == [text]  # the transcript keeps every word


@pytest.mark.parametrize("profile", ["compact", "cached"])
async def test_long_turn_is_whole_in_either_prompt_profile(monkeypatch, order, merchant, profile):
    from app.voice.providers import settings as provider_settings

    pinned = provider_settings.get_provider_settings().model_copy(update={"llm_prompt_profile": profile})
    monkeypatch.setattr(provider_settings, "get_provider_settings", lambda: pinned)
    fast_timing(monkeypatch)
    call = build_call(monkeypatch, order, merchant, script=[reply("Thanks, noted.")], silence_seconds=30)
    full = " ".join(monologue())
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.stt.says(full)
        await wait_until(lambda: "Thanks, noted." in call.agent_lines(), what="answer")
    assert call.llm.user_messages(0)[-1] == full


def test_clip_turn_is_a_no_op_below_the_cap():
    assert clip_turn("short and sweet") == "short and sweet"
    long = " ".join(f"word{i}" for i in range(3000))
    clipped = clip_turn(long, 1000)
    assert len(clipped) <= 1000 and clipped.startswith("word0 word1") and clipped.endswith("word2998 word2999")


async def test_long_real_sentence_is_not_mistaken_for_a_hallucination_loop(monkeypatch, order, merchant):
    call = build_call(monkeypatch, order, merchant)
    story = (
        "so I came home on tuesday and then I saw water under the sink and then I tried to tighten the pipe "
        "and then it got worse and then I turned off the valve under the counter before the floor flooded"
    )
    assert call.bridge._phantom_transcript_reason(story) is None
    assert call.bridge._phantom_transcript_reason("thank you " * 12) == "ignored_stt_noise_hallucination"
    assert call.bridge._phantom_transcript_reason("I'm going to " * 7) == "ignored_stt_noise_hallucination"
    assert call.bridge._phantom_transcript_reason("thanks for watching") == "ignored_stt_noise_hallucination"


async def test_scripted_llm_reports_cancellations():
    llm = ScriptedLLM([Slow(5.0, reply("never"))])
    task = asyncio.create_task(llm.complete([{"role": "user", "content": "hi"}]))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert llm.cancelled == 1
