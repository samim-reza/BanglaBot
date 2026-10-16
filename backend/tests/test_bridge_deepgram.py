"""The real ``DeepgramSTT`` inside the bridge, against a fake Deepgram socket.

Telnyx frames go through the bridge's media loop into the session, whose energy VAD
sends ``Finalize`` after ~600 ms of quiet. Deepgram answers with a ``from_finalize``
final — and may still send its own late ``speech_final`` / ``UtteranceEnd`` for the
same audio, or have endpointed part of the sentence first. Either way the caller's
sentence must become exactly ONE turn.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from app.voice.audio import ulaw_rms
from app.voice.codec import linear_to_ulaw
from app.voice.providers.stt.deepgram import DeepgramSTT
from tests.bridge_fakes import reply, wait_until
from tests.bridge_harness import build_call, fast_timing

SPEECH = base64.b64encode(bytes([linear_to_ulaw(6000)]) * 160).decode("ascii")
QUIET = base64.b64encode(b"\xff" * 160).decode("ascii")


def _results(text: str, *, is_final: bool, **flags: Any) -> str:
    return json.dumps({"type": "Results", "is_final": is_final, **flags, "channel": {"alternatives": [{"transcript": text}]}})


class FakeDeepgram:
    """Deepgram's listen socket: interim words while the audio is loud, finals on Finalize.

    ``utterances`` holds one entry per sentence: the full text, or ``(endpointed, rest)``
    when Deepgram's own endpointing finalizes the first part ~300 ms into the pause.
    """

    def __init__(self, utterances: list[Any]) -> None:
        self.utterances = list(utterances)
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.finalizes = 0
        self._speaking = False
        self._quiet = 0

    async def connect(self, url: str, **kwargs: Any) -> "FakeDeepgram":
        return self

    def _emit(self, message: str) -> None:
        self.inbox.put_nowait(message)

    async def send(self, message: str | bytes) -> None:
        if isinstance(message, (bytes, bytearray)):
            loud = ulaw_rms(bytes(message)) > 1000
            if loud and not self._speaking and self.utterances:
                self._speaking, self._quiet = True, 0
                self._emit(json.dumps({"type": "SpeechStarted"}))
                first = self.utterances[0] if isinstance(self.utterances[0], str) else self.utterances[0][0]
                self._emit(_results(first.split()[0], is_final=False))
            elif self._speaking:
                self._quiet = 0 if loud else self._quiet + 1
                current = self.utterances[0]
                if self._quiet == 15 and isinstance(current, tuple):  # Deepgram endpointing (300 ms)
                    self._emit(_results(current[0], is_final=True, speech_final=True))
            return
        data = json.loads(message)
        if data.get("type") == "Finalize" and self._speaking:
            self.finalizes += 1
            self._speaking = False
            current = self.utterances.pop(0)
            self._emit(_results(current if isinstance(current, str) else current[1], is_final=True, from_finalize=True))
            # Deepgram's own, late end-of-speech for the same audio: must not make a second turn.
            self._emit(_results("", is_final=True, speech_final=True))
            self._emit(json.dumps({"type": "UtteranceEnd", "last_word_end": 1.2}))
        elif data.get("type") == "CloseStream":
            self._emit(None)  # type: ignore[arg-type]

    async def close(self) -> None:
        self._emit(None)  # type: ignore[arg-type]

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        item = await self.inbox.get()
        if item is None:
            raise StopAsyncIteration
        return item


def _deepgram_call(monkeypatch, order, merchant, server: FakeDeepgram, script):
    async def open_stt(**kwargs):
        stt = DeepgramSTT(api_key="dg-test", language="en", end_silence_ms=600, connector=server.connect)
        await stt.connect()
        return stt

    return build_call(monkeypatch, order, merchant, script=script, open_stt=open_stt, silence_seconds=30)


async def test_vad_finalize_and_late_deepgram_endings_make_one_turn(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    sentence = "I need to move the delivery to Friday afternoon"
    answer = "Friday afternoon works. Shall I change it?"
    server = FakeDeepgram([sentence])
    call = _deepgram_call(monkeypatch, order, merchant, server, [reply(answer)])
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.ws.media(SPEECH, 40)  # 0.8 s of speech
        await call.ws.media(QUIET, 20)  # 0.4 s: a pause, not the end
        assert server.finalizes == 0
        await call.ws.media(QUIET, 15)  # past 600 ms of quiet: the VAD flushes now
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
        await asyncio.sleep(0.3)  # the late speech_final / UtteranceEnd have arrived
    assert server.finalizes == 1
    assert call.customer_lines() == [sentence] and len(call.llm.calls) == 1


async def test_endpointed_half_and_finalized_rest_are_one_turn(monkeypatch, order, merchant):
    # Real merge window: Deepgram's endpointing (300 ms) and the VAD Finalize (600 ms) land
    # ~300 ms apart on a live line, inside TURN_MERGE_SECONDS.
    fast_timing(monkeypatch, TURN_MERGE_SECONDS=0.4)
    first, rest = "I need to move the delivery", "to Friday afternoon please"
    answer = "Friday afternoon works. Shall I change it?"
    server = FakeDeepgram([(first, rest)])
    call = _deepgram_call(monkeypatch, order, merchant, server, [reply(answer)])
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.ws.media(SPEECH, 40, pace=0.015)
        await call.ws.media(QUIET, 35, pace=0.015)  # ~real time: the two finals land ~225-300 ms apart
        await wait_until(lambda: answer in call.agent_lines(), what="answer")
        await asyncio.sleep(0.3)
    assert len(call.llm.calls) == 1 and call.llm.user_messages(0)[-1] == f"{first} {rest}"


async def test_two_sentences_with_a_real_pause_are_two_turns(monkeypatch, order, merchant):
    fast_timing(monkeypatch)
    one, two = "I need to move the delivery to Friday", "and please ring the bell twice"
    server = FakeDeepgram([one, two])
    call = _deepgram_call(monkeypatch, order, merchant, server, [reply("Sure, Friday it is."), reply("Noted, I will add that.")])
    async with call.running():
        await wait_until(call.opening_done, what="opening")
        await call.ws.media(SPEECH, 30)
        await call.ws.media(QUIET, 35)
        await wait_until(lambda: "Sure, Friday it is." in call.agent_lines(), what="first answer")
        await call.ws.media(SPEECH, 30)
        await call.ws.media(QUIET, 35)
        await wait_until(lambda: "Noted, I will add that." in call.agent_lines(), what="second answer")
    assert server.finalizes == 2 and call.customer_lines() == [one, two] and len(call.llm.calls) == 2
