"""Pure-Python drive of ``CallBridge``: no database, no network.

Every external edge is a fake — the Twilio websocket, the transcription
stream, the chat model, the TTS engine and the call store — so the tests
exercise the bridge's own turn-taking: greeting + first question → caller
turn → save_details → narration → "yes" → confirm_order → closing → hangup;
the unclear-answer ladder; barge-in; and the two-strike silence drop.
"""

from __future__ import annotations

import asyncio
import base64
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.flows.base import OUTCOME_AUTO_DROPPED, OUTCOME_CONFIRMED, OUTCOME_UNCLEAR
from app.voice import bridge as bridge_module
from app.voice.audio import speech_units
from app.voice.bridge import CallBridge
from app.voice.languages import phrase
from app.voice.llm import LLMReply, LLMToolCall
from app.voice.stt import STTEvent
from app.voice.tools import NullCallStore

SILENT_FRAME = base64.b64encode(b"\xff" * 160).decode("ascii")
LOUD_FRAME = base64.b64encode(b"\x00\x80" * 80).decode("ascii")


async def wait_until(predicate, *, timeout: float = 5.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.closed = False

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)
        if message.get("event") == "mark":
            await self.inbound.put({"event": "mark", "mark": {"name": message["mark"]["name"]}})

    async def receive_json(self) -> dict[str, Any]:
        return await self.inbound.get()

    async def close(self, code: int | None = None) -> None:
        self.closed = True
        await self.inbound.put({"event": "stop"})

    def media_payloads(self) -> list[str]:
        return [m["media"]["payload"] for m in self.sent if m.get("event") == "media"]

    def marks(self) -> list[str]:
        return [m["mark"]["name"] for m in self.sent if m.get("event") == "mark"]

    def clears(self) -> int:
        return sum(1 for m in self.sent if m.get("event") == "clear")

    async def push_frames(self, payload: str, count: int) -> None:
        for _ in range(count):
            await self.inbound.put({"event": "media", "media": {"payload": payload}})
            await asyncio.sleep(0.001)


class FakeSTT:
    instances: list["FakeSTT"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.events_in: asyncio.Queue[STTEvent] = asyncio.Queue()
        self.audio: list[str] = []
        self.connected = False
        self.closed = False
        self.session_id = "sess"
        FakeSTT.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def send_audio_b64(self, payload: str) -> None:
        self.audio.append(payload)

    async def events(self):
        while True:
            event = await self.events_in.get()
            yield event
            if event.type == "closed":
                return

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            await self.events_in.put(STTEvent("closed"))

    async def caller_says(self, text: str, item_id: str = "i") -> None:
        await self.events_in.put(STTEvent("speech_started", item_id=item_id))
        await self.events_in.put(STTEvent("speech_stopped", item_id=item_id))
        await self.events_in.put(STTEvent("completed", text=text, item_id=item_id))


class FakeLLM:
    def __init__(self, replies: list[LLMReply], **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.replies = list(replies)
        self.calls: list[list[dict[str, Any]]] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_prompt_tokens = 0
        self.closed = False

    async def complete(self, messages, *, tools=None, tool_choice="auto", temperature=None) -> LLMReply:
        self.calls.append([dict(m) for m in messages])
        assert tools, "tools must be attached to every request"
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        self.prompt_tokens += 100
        self.completion_tokens += 10
        return self.replies.pop(0)

    def stats(self) -> dict[str, Any]:
        return {"requests": len(self.calls)}

    async def aclose(self) -> None:
        self.closed = True


class FakeTTS:
    def __init__(self, audio: bytes = b"\x10" * 480) -> None:
        self.audio = audio
        self.synthesized: list[tuple[str, str | None, str | None]] = []
        self.warmed: list[str] = []

    async def synthesize(self, text: str, *, language=None, persona=None, voice=None) -> bytes:
        self.synthesized.append((text, language, persona))
        return self.audio

    async def warm(self, lines, *, language, persona, voice=None) -> int:
        self.warmed.extend(line for line in lines if line)
        return 0

    def stats(self) -> dict[str, Any]:
        return {"synth_count": len(self.synthesized)}


def _reply(content: str = "", tool_calls: list[LLMToolCall] | None = None) -> LLMReply:
    return LLMReply(content=content, tool_calls=tool_calls or [], usage={}, assistant_message={}, finish_reason="stop")


def _tool(call_id: str, name: str, arguments: str = "{}") -> LLMToolCall:
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


@dataclass
class Harness:
    bridge: CallBridge
    ws: FakeWebSocket
    tts: FakeTTS
    store: NullCallStore
    llm_holder: dict[str, FakeLLM] = field(default_factory=dict)

    @property
    def stt(self) -> FakeSTT:
        return FakeSTT.instances[-1]

    @property
    def llm(self) -> FakeLLM:
        return self.llm_holder["llm"]

    def agent_lines(self) -> list[str]:
        return [text for role, text in self.bridge.transcript_lines if role == "Agent"]

    def customer_lines(self) -> list[str]:
        return [text for role, text in self.bridge.transcript_lines if role == "Customer"]

    @asynccontextmanager
    async def running(self):
        task = asyncio.create_task(self.bridge.run())
        try:
            yield task
        finally:
            if not task.done():
                task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


def _build(monkeypatch: pytest.MonkeyPatch, order, merchant, *, replies: list[LLMReply], tts: FakeTTS | None = None) -> Harness:
    ws = FakeWebSocket()
    tts = tts or FakeTTS()
    store = NullCallStore()
    llm_holder: dict[str, FakeLLM] = {}
    FakeSTT.instances.clear()

    def fake_llm_factory(**kwargs):
        llm = FakeLLM(replies, **kwargs)
        llm_holder["llm"] = llm
        return llm

    monkeypatch.setattr(bridge_module, "TranscriptionStream", FakeSTT)
    monkeypatch.setattr(bridge_module, "ChatLLM", fake_llm_factory)
    monkeypatch.setattr(bridge_module, "get_tts", lambda: tts)
    bridge = CallBridge(
        ws,  # type: ignore[arg-type]
        order=order,
        merchant=merchant,
        call_log_id="log-1",
        stream_sid="MZ_test",
        call_sid="",  # no Twilio hangup fallback → no network
        store=store,
    )
    bridge.settings = bridge.settings.model_copy(update={"openai_api_key": "sk-test", "azure_speech_key": "azure-test", "voice_instant_ack": False})
    bridge._goodbye_playback_tail_seconds = 0.05
    return Harness(bridge=bridge, ws=ws, tts=tts, store=store, llm_holder=llm_holder)


@pytest.mark.asyncio
async def test_happy_path_identity_then_confirmation(monkeypatch, order, merchant):
    narration = "ধন্যবাদ। আপনি একটি পাঞ্জাবি অর্ডার করেছেন, মোট এক হাজার আটশো পঞ্চাশ টাকা ক্যাশ অন ডেলিভারি। অর্ডারটি কি কনফার্ম করব?"
    replies = [
        _reply(tool_calls=[_tool("c1", "save_details", '{"identity_confirmed": true}')]),
        _reply(content=narration),
    ]
    h = _build(monkeypatch, order, merchant, replies=replies)
    opening = f"{phrase('greeting', 'bn', business_name='Demo Shop')} {phrase('opening_question', 'bn', customer_name=order.customer_name)}"
    async with h.running() as run_task:
        # --- greeting + first question spoken from the cache-warmed lines, framed and marked ---
        await wait_until(lambda: h.agent_lines() == [opening], what="opening transcript")
        assert h.tts.synthesized[0][1:] == ("bn", "female")
        frames = h.ws.media_payloads()
        assert frames and all(len(base64.b64decode(f)) == 160 for f in frames)
        assert h.ws.marks() == ["agent-1"]
        assert h.stt.connected and h.stt.kwargs["language"] == "bn"  # pinned to the merchant language
        # Warmed at the same per-sentence granularity the speaker synthesizes, in both languages.
        assert all(unit in h.tts.warmed for unit in speech_units(opening))
        assert [t for t, _, _ in h.tts.synthesized[: len(speech_units(opening))]] == speech_units(opening)
        assert all(s in h.tts.warmed for s in speech_units(phrase("closing_confirmed", "bn")))
        # Three system messages, most stable first (prompt caching); the first step's directive is in the call part.
        assert [m["role"] for m in h.bridge.messages[:3]] == ["system", "system", "system"]
        assert "[ধাপ পরিবর্তন]" in h.bridge.messages[2]["content"] and "[ধাপ পরিবর্তন]" not in h.bridge.messages[0]["content"]

        # --- caller: "yes speaking" → save_details → node directive → narration ---
        await h.ws.push_frames(SILENT_FRAME, 3)
        await h.stt.caller_says("জি, আমি বলছি", item_id="i1")
        await wait_until(lambda: narration in h.agent_lines(), what="narration")
        assert h.customer_lines() == ["জি, আমি বলছি"]
        assert h.stt.audio[:3] == [SILENT_FRAME] * 3
        second = h.llm.calls[1]
        roles = [m["role"] for m in second]
        assert roles == ["system", "system", "system", "assistant", "user", "assistant", "tool", "system"]
        assert second[6]["tool_call_id"] == "c1" and '"instruction"' in second[6]["content"]
        assert h.bridge.runtime.current_node == "decision"

        # --- caller: a clean "yes" → confirm_order straight from the fast path (no model) → closing → hangup ---
        await h.stt.caller_says("হ্যাঁ, ঠিক আছে", item_id="i2")
        await asyncio.wait_for(run_task, timeout=8.0)
        assert len(h.llm.calls) == 2
        assert h.bridge.outcome == OUTCOME_CONFIRMED
        assert h.agent_lines()[-1] == phrase("closing_confirmed", "bn")
        assert h.bridge.closed and h.bridge._closed_by_agent and h.ws.closed
        assert h.ws.marks() == ["agent-1", "agent-2", "agent-3"]
        assert h.bridge.messages[-1] == {"role": "assistant", "content": phrase("closing_confirmed", "bn")}
        assert h.stt.closed and h.llm.closed
        # Persistence: outcome, transcript, usage.
        assert h.store.outcomes[-1]["status"] == "confirmed" and h.store.outcomes[-1]["final_node"] == "wrap_up"
        assert h.store.transcripts[-1]["transcript"].startswith(f"Agent: {opening}\nCustomer: জি, আমি বলছি")
        assert h.store.usage[-1]["llm_prompt_tokens"] == 200 and h.store.usage[-1]["tts_chars"] > 0


@pytest.mark.asyncio
async def test_unclear_answer_ladder_ends_in_needs_review(monkeypatch, order, merchant):
    replies = [
        _reply(tool_calls=[_tool("c1", "save_details", '{"identity_confirmed": true}')]),
        _reply(content="আপনি একটি পাঞ্জাবি অর্ডার করেছেন। অর্ডারটি কি কনফার্ম করব?"),
        _reply(tool_calls=[_tool("c2", "confirm_order")]),
        _reply(tool_calls=[_tool("c3", "confirm_order")]),
        _reply(tool_calls=[_tool("c4", "cancel_order")]),
    ]
    h = _build(monkeypatch, order, merchant, replies=replies)
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("হ্যাঁ বলছি", item_id="i1")
        await wait_until(lambda: len(h.agent_lines()) == 2, what="decision question")
        await h.stt.caller_says("মানে কী বললেন", item_id="i2")
        await wait_until(lambda: phrase("decision_reask_1", "bn") in h.agent_lines(), what="first re-ask")
        # The re-ask was spoken by the backend, not the model, and the model saw it.
        assert h.bridge.messages[-1] == {"role": "assistant", "content": phrase("decision_reask_1", "bn")}
        await h.stt.caller_says("কিসের কথা", item_id="i3")
        await wait_until(lambda: phrase("decision_reask_2", "bn") in h.agent_lines(), what="second re-ask")
        await h.stt.caller_says("বুঝলাম না ভাই", item_id="i4")
        await asyncio.wait_for(run_task, timeout=8.0)
        assert h.bridge.outcome == OUTCOME_UNCLEAR
        assert h.agent_lines()[-1] == phrase("closing_unclear", "bn")
        assert h.store.outcomes[-1]["status"] == "needs_review"
        assert h.ws.closed


@pytest.mark.asyncio
async def test_english_merchant_runs_the_call_in_english(monkeypatch, order, merchant):
    order.customer_name = "Nusrat Jahan"
    merchant.language = "en"
    replies = [
        _reply(tool_calls=[_tool("c1", "save_details", '{"identity_confirmed": true}')]),
        _reply(content="Great. You ordered one panjabi for 1850 taka, cash on delivery. Shall I confirm the order?"),
        _reply(tool_calls=[_tool("c2", "confirm_order")]),
    ]
    h = _build(monkeypatch, order, merchant, replies=replies)
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("Yes, this is Nusrat speaking", item_id="i1")
        await wait_until(lambda: len(h.agent_lines()) == 2, what="narration")
        assert h.bridge.active_language == "en" and h.bridge.runtime.language == "en"
        assert h.stt.kwargs["language"] == "en"
        # The save_details instruction is in the merchant's language.
        tool_msg = [m for m in h.bridge.messages if m["role"] == "tool"][-1]
        assert "cash on delivery" in tool_msg["content"]
        assert h.tts.synthesized[-1][1] == "en"
        await h.stt.caller_says("Yes please, confirm it", item_id="i2")
        await asyncio.wait_for(run_task, timeout=8.0)
        assert h.agent_lines()[-1] == phrase("closing_confirmed", "en")
        assert h.store.outcomes[-1]["language"] == "en"


@pytest.mark.asyncio
async def test_sustained_loud_caller_audio_interrupts_playback(monkeypatch, order, merchant):
    h = _build(monkeypatch, order, merchant, replies=[_reply(content="জি।")], tts=FakeTTS(audio=b"\x10" * 8000 * 3))
    h.bridge.settings = h.bridge.settings.model_copy(update={"voice_barge_in_min_frames": 5, "voice_barge_in_min_rms": 500})
    async with h.running() as run_task:
        await wait_until(lambda: h.bridge.assistant_speaking and len(h.ws.media_payloads()) > 10, what="opening playing")
        # The opening is protected; end it early and interrupt a normal line instead.
        h.bridge._current_utterance.interrupted = True
        await wait_until(lambda: not h.bridge.assistant_speaking, what="opening stopped")
        h.bridge.speak("আপনার ঠিকানাটা একটু মিলিয়ে নিই, ঠিকানাটা কি ঠিক আছে?")
        await wait_until(lambda: h.bridge.assistant_speaking and h.bridge._barge_in_allowed, what="line playing")
        sent_before = len(h.ws.media_payloads())
        await h.ws.push_frames(LOUD_FRAME, 12)
        await wait_until(lambda: h.ws.clears() >= 1, what="clear on barge-in")
        await wait_until(lambda: not h.bridge.assistant_speaking, what="playback stopped")
        assert len(h.stt.audio) >= 5
        await asyncio.sleep(0.1)
        assert len(h.ws.media_payloads()) <= sent_before + 2
        await h.ws.inbound.put({"event": "stop"})
        await asyncio.wait_for(run_task, timeout=5.0)
        assert h.bridge.closed and not h.bridge._closed_by_agent
        assert h.bridge.outcome == ""  # caller hung up: the status callback settles the order


@pytest.mark.asyncio
async def test_two_strike_silence_drops_the_call(monkeypatch, order, merchant):
    merchant.silence_hangup_secs = 5  # clamped to the 3 s floor below
    h = _build(monkeypatch, order, merchant, replies=[])
    monkeypatch.setattr(CallBridge, "silence_seconds", property(lambda self: 1))
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await wait_until(lambda: phrase("still_there", "bn") in h.agent_lines(), timeout=6.0, what="still-there re-ask")
        await asyncio.wait_for(run_task, timeout=8.0)
        assert h.bridge.outcome == OUTCOME_AUTO_DROPPED
        assert h.agent_lines()[-1] == phrase("closing_dropped", "bn")
        assert h.store.outcomes[-1]["status"] == "no_answer"
        assert h.ws.closed


@pytest.mark.asyncio
async def test_echoed_agent_line_and_noise_are_ignored(monkeypatch, order, merchant):
    h = _build(monkeypatch, order, merchant, replies=[])
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("আমি কি রাহিম উদ্দিন এর সাথে কথা বলছি", item_id="e1")  # our own question echoed back
        await h.stt.caller_says("Thank you for watching", item_id="e2")
        await asyncio.sleep(0.8)
        assert h.customer_lines() == [] and not h.llm_holder["llm"].calls
        await h.ws.inbound.put({"event": "stop"})
        await asyncio.wait_for(run_task, timeout=5.0)


@pytest.mark.asyncio
async def test_transfer_dials_support_after_transfer_line(monkeypatch, order, merchant):
    merchant.support_phone = "01999999999"
    replies = [
        _reply(tool_calls=[_tool("c1", "save_details", '{"identity_confirmed": true}')]),
        _reply(content="আপনি একটি পাঞ্জাবি অর্ডার করেছেন। অর্ডারটি কি কনফার্ম করব?"),
        _reply(tool_calls=[_tool("c2", "transfer_to_human", '{"reason": "discount"}')]),
    ]
    h = _build(monkeypatch, order, merchant, replies=replies)
    dialed: list[str] = []

    async def fake_dial(self, number: str) -> bool:
        dialed.append(number)
        return True

    monkeypatch.setattr(CallBridge, "_dial_support", fake_dial)
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("জি বলছি", item_id="i1")
        await wait_until(lambda: len(h.agent_lines()) == 2, what="decision")
        await h.stt.caller_says("আমি একজন মানুষের সাথে কথা বলতে চাই, ডিসকাউন্ট নিয়ে", item_id="i2")
        await asyncio.wait_for(run_task, timeout=8.0)
        assert dialed == ["01999999999"]
        assert h.agent_lines()[-1] == phrase("closing_transfer", "bn")
        assert h.store.outcomes[-1]["outcome"] == "transfer" and h.store.outcomes[-1]["status"] == "needs_review"


# --- latency: fast path + instant ack ------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_yes_uses_prepared_line_without_the_model(monkeypatch, order, merchant):
    """A clean "yes" at the identity step speaks the pre-composed confirmation question
    straight from the cache — no save_details / narration round-trips."""
    from app.voice import prepared

    prepared.clear()
    line = "আপনি একটি পাঞ্জাবি অর্ডার করেছেন, মোট এক হাজার আটশো পঞ্চাশ টাকা ক্যাশ অন ডেলিভারিতে। অর্ডারটি কি কনফার্ম করব?"
    prepared.put_decision_line(order.id, "bn", line)
    h = _build(monkeypatch, order, merchant, replies=[])  # the model must never be called
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("হ্যাঁ।", item_id="i1")
        await wait_until(lambda: line in h.agent_lines(), what="prepared decision line")
        assert h.llm.calls == []
        assert h.bridge.runtime.slots.get("identity_confirmed") is True
        assert h.bridge.runtime.stage == "decision"
        roles = [m["role"] for m in h.bridge.messages]
        assert roles[-3:] == ["user", "system", "assistant"]  # user → step directive → spoken line
        assert h.bridge.messages[-1]["content"] == line
    prepared.clear()


@pytest.mark.asyncio
async def test_identity_yes_without_prepared_line_falls_back_to_the_model(monkeypatch, order, merchant):
    from app.voice import prepared

    prepared.clear()
    narration = "আপনি একটি পাঞ্জাবি অর্ডার করেছেন। কনফার্ম করব?"
    replies = [
        _reply(tool_calls=[_tool("c1", "save_details", '{"identity_confirmed": true}')]),
        _reply(content=narration),
    ]
    h = _build(monkeypatch, order, merchant, replies=replies)
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("হ্যাঁ।", item_id="i1")
        await wait_until(lambda: narration in h.agent_lines(), what="narration")
        assert len(h.llm.calls) == 2


@pytest.mark.asyncio
async def test_instant_ack_precedes_the_model_reply(monkeypatch, order, merchant):
    from app.voice import prepared

    prepared.clear()
    narration = "আপনি একটি পাঞ্জাবি অর্ডার করেছেন। কনফার্ম করব?"
    replies = [_reply(content=narration)]
    h = _build(monkeypatch, order, merchant, replies=replies)
    h.bridge.settings = h.bridge.settings.model_copy(update={"voice_instant_ack": True})
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("আমার একটা প্রশ্ন আছে", item_id="i1")
        await wait_until(lambda: narration in h.agent_lines(), what="narration")
        lines = h.agent_lines()
        assert lines[1] == phrase("ack", "bn") and lines[2] == narration
        # The ack is spoken, not part of the model's conversation history.
        assert all(m.get("content") != phrase("ack", "bn") for m in h.bridge.messages)


# --- rejected / forwarded call --------------------------------------------------------------


@pytest.mark.asyncio
async def test_forwarded_call_is_hung_up_and_marked_diverted(monkeypatch, order, merchant):
    """The callee rejected and the carrier forwarded the call to a divert service:
    Twilio reports forwarded_from, so the bridge hangs up at once instead of talking to it."""
    from app.services import call_service

    hung_up: list[str] = []

    async def fake_details(call_sid: str):
        return {"status": "in-progress", "answered_by": "", "forwarded_from": "+8809999999999"}  # a different number

    async def fake_complete(call_sid: str):
        hung_up.append(call_sid)

    monkeypatch.setattr(call_service, "fetch_call_details", fake_details)
    monkeypatch.setattr(call_service, "complete_call", fake_complete)
    h = _build(monkeypatch, order, merchant, replies=[])
    h.bridge.settings = h.bridge.settings.model_copy(update={"voice_hangup_on_forwarded": True})
    h.bridge.call_sid = "CA_forwarded"
    async with h.running() as run_task:
        await wait_until(lambda: h.ws.closed, what="hangup")
        await asyncio.wait_for(run_task, timeout=5.0)
    assert h.store.outcomes and h.store.outcomes[-1]["outcome"] == "diverted"
    assert h.store.outcomes[-1]["status"] == "no_answer"
    assert hung_up == ["CA_forwarded"]
    assert h.llm.calls == []


@pytest.mark.asyncio
async def test_normal_call_is_not_treated_as_forwarded(monkeypatch, order, merchant):
    """Carriers stamp forwarded_from with the dialed number on ordinary calls — never hang up on that."""
    from app.services import call_service

    async def fake_details(call_sid: str):
        return {"status": "in-progress", "answered_by": "human", "forwarded_from": order.customer_phone}

    monkeypatch.setattr(call_service, "fetch_call_details", fake_details)
    h = _build(monkeypatch, order, merchant, replies=[])
    h.bridge.settings = h.bridge.settings.model_copy(update={"voice_hangup_on_forwarded": True})
    h.bridge.call_sid = "CA_direct"
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await asyncio.sleep(0.2)
        assert not h.ws.closed and h.store.outcomes == []


@pytest.mark.asyncio
async def test_confirmation_then_address_check_then_goodbye(monkeypatch, order, merchant):
    """verify_address on: yes → order question (prepared) → yes → confirm_order asks the
    address (backend line) → yes → closing line, all without extra model round-trips."""
    from app.voice import prepared

    prepared.clear()
    merchant.verify_address = True
    decision_line = "আপনি একটি পাঞ্জাবি অর্ডার করেছেন, মোট এক হাজার আটশো পঞ্চাশ টাকা। অর্ডারটি কি কনফার্ম করব?"
    prepared.put_decision_line(order.id, "bn", decision_line)
    h = _build(monkeypatch, order, merchant, replies=[])
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("জি বলছি", item_id="i1")
        await wait_until(lambda: decision_line in h.agent_lines(), what="decision line")
        await h.stt.caller_says("হ্যাঁ, কনফার্ম", item_id="i2")
        address_q = phrase("address_question", "bn", address=order.address)
        await wait_until(lambda: address_q in h.agent_lines(), what="address question after the yes")
        assert h.bridge.outcome == OUTCOME_CONFIRMED and h.bridge.runtime.stage == "address"
        assert len(h.llm.calls) == 0  # the clean "yes" went straight to confirm_order
        await h.stt.caller_says("হ্যাঁ ঠিক আছে", item_id="i3")
        closing = phrase("closing_confirmed", "bn")
        await wait_until(lambda: closing in h.agent_lines(), what="closing")
        await asyncio.wait_for(run_task, timeout=6.0)
        assert h.bridge.closed and h.bridge._closed_by_agent
        assert len(h.llm.calls) == 0  # no turn of this call needed the model
        assert h.store.outcomes[-1]["status"] == "confirmed"
        assert h.store.outcomes[-1]["flow_data"].get("address_correct") is True
    prepared.clear()


# --- identity denials ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bare_no_asks_whether_they_know_the_customer_then_hangs_up(monkeypatch, order, merchant):
    """"না" to the identity question is not a wrong number: the backend asks whether
    they know the customer; "চিনি না" then closes the call as a wrong number — no model."""
    h = _build(monkeypatch, order, merchant, replies=[])
    knows_q = phrase("knows_person_question", "bn", customer_name=order.customer_name)
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("না।", item_id="i1")
        await wait_until(lambda: knows_q in h.agent_lines(), what="knows-person question")
        assert h.bridge.runtime.stage == "knows_person"
        assert phrase("ack", "bn") not in h.agent_lines()  # no "হ্যাঁ" on top of a "না"
        await h.stt.caller_says("না, চিনি না", item_id="i2")
        closing = phrase("closing_wrong_number", "bn") if phrase("closing_wrong_number", "bn") else None
        await wait_until(lambda: h.bridge.outcome == "wrong_number", what="wrong-number outcome")
        await asyncio.wait_for(run_task, timeout=6.0)
        assert h.bridge.closed and h.bridge._closed_by_agent
        assert h.llm.calls == []
        assert h.store.outcomes[-1]["status"] == "needs_review"
        assert closing is None or closing in h.agent_lines()


@pytest.mark.asyncio
async def test_knows_the_customer_relays_and_hangs_up(monkeypatch, order, merchant):
    h = _build(monkeypatch, order, merchant, replies=[])
    async with h.running() as run_task:
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("না, আমি ওর ভাই", item_id="i1")
        await wait_until(lambda: h.bridge.runtime.stage in ("knows_person", "relay"), what="identity denied")
        if h.bridge.runtime.stage == "knows_person":
            await h.stt.caller_says("হ্যাঁ চিনি", item_id="i2")
        await wait_until(lambda: h.bridge.outcome == "relay", what="relay outcome")
        await asyncio.wait_for(run_task, timeout=6.0)
        assert h.bridge.closed and h.bridge._closed_by_agent
        assert h.llm.calls == []


# --- language stability -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_garbled_english_transcript_does_not_switch_the_call_to_english(monkeypatch, order, merchant):
    """STT once heard "জ্বি বলছিলেন" as "Do you bulletin?": the call must stay in Bangla."""
    replies = [_reply(content="দুঃখিত, আবার বলবেন?")]
    h = _build(monkeypatch, order, merchant, replies=replies)
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        assert h.stt.kwargs["language"] == "bn"  # transcriber pinned to the primary language
        await h.stt.caller_says("Do you bulletin?", item_id="i1")
        await wait_until(lambda: len(h.agent_lines()) == 2, what="reply")
        assert h.bridge.active_language == "bn" and h.bridge.runtime.language == "bn"
        assert h.tts.synthesized[-1][1] == "bn"


@pytest.mark.asyncio
async def test_english_turns_never_switch_a_bangla_merchant(monkeypatch, order, merchant):
    """The merchant chose Bangla: the call stays Bangla whatever the transcripts look like."""
    replies = [_reply(content="দুঃখিত, আবার বলবেন?"), _reply(content="দুঃখিত, বাংলায় বলবেন?")]
    h = _build(monkeypatch, order, merchant, replies=replies)
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        await h.stt.caller_says("Yes, this is Nusrat speaking", item_id="i1")
        await wait_until(lambda: len(h.agent_lines()) == 2, what="first reply")
        await h.stt.caller_says("speak english please", item_id="i2")
        await wait_until(lambda: len(h.agent_lines()) == 3, what="second reply")
        assert h.bridge.active_language == "bn" and h.bridge.runtime.language == "bn"
        assert all(lang == "bn" for _, lang, _ in h.tts.synthesized)


@pytest.mark.asyncio
async def test_transcriber_gets_the_call_vocabulary_but_echo_guard_uses_the_generic_prompt(monkeypatch, order, merchant):
    order.items_summary = "কটন শাড়ি x2"
    h = _build(monkeypatch, order, merchant, replies=[])
    async with h.running():
        await wait_until(lambda: len(h.agent_lines()) == 1, what="opening")
        prompt = h.stt.kwargs["prompt"]
        assert order.customer_name in prompt and merchant.business_name in prompt and "কটন শাড়ি" in prompt
        assert prompt.startswith(phrase("transcription_prompt", "bn"))
        # A caller saying the customer's own name is a real answer, not a prompt echo.
        assert h.bridge._phantom_transcript_reason(f"হ্যাঁ আমি {order.customer_name} বলছি") is None


@pytest.mark.asyncio
async def test_greeting_plays_before_the_transcriber_is_connected(monkeypatch, order, merchant):
    """Answer → voice within a second: the opening must not wait for the STT socket."""
    gate = asyncio.Event()

    async def slow_connect(self):
        await gate.wait()
        self.connected = True

    monkeypatch.setattr(FakeSTT, "connect", slow_connect)
    h = _build(monkeypatch, order, merchant, replies=[], tts=FakeTTS(audio=b"\x10" * 8000))
    async with h.running():
        await wait_until(lambda: len(h.ws.media_payloads()) > 5, what="greeting audio")
        assert not h.stt.connected  # audio already flowing while the STT is still connecting
        gate.set()
        await wait_until(lambda: h.stt.connected, what="stt connected")
