"""Scripted stand-ins for the paid edges: the LLM chain, the STT stream, the TTS chain and the
owner's webhook receiver. Everything else in the e2e run is the real code.

``FakeProviders.install(monkeypatch)`` swaps them in at every import site the engine uses
(the bridge, text sessions, warm-up, previews), so a call or chat never leaves the process.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.voice.llm import LLMReply, LLMToolCall
from app.voice.stt import STTEvent

#: 60 ms of μ-law per synthesized sentence: real framing, near-instant playout.
FAKE_AUDIO = b"\x10" * 480
LLM_KEY = "groq:openai/gpt-oss-120b"


def tool_reply(name: str, arguments: dict[str, Any] | None = None, *, call_id: str = "") -> LLMReply:
    call = LLMToolCall(id=call_id or f"call_{name}", name=name, arguments=json.dumps(arguments or {}))
    return LLMReply(content="", tool_calls=[call], usage={"prompt_tokens": 900, "completion_tokens": 40}, assistant_message={}, finish_reason="tool_calls")


def text_reply(content: str) -> LLMReply:
    return LLMReply(content=content, tool_calls=[], usage={"prompt_tokens": 900, "completion_tokens": 20}, assistant_message={}, finish_reason="stop")


class ScriptedLLM:
    """Pops scripted replies in order; every request is kept for assertions."""

    model = "openai/gpt-oss-120b"
    provider = "groq"

    def __init__(self, replies: list[LLMReply], **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_prompt_tokens = 0
        self.exhausted = False
        self.closed = False

    async def complete(self, messages, *, tools=None, tool_choice="auto", temperature=None) -> LLMReply:  # noqa: ANN001
        self.requests.append({"messages": [dict(m) for m in messages], "tools": [t["function"]["name"] for t in tools or []]})
        if self.replies:
            reply = self.replies.pop(0)
        else:
            self.exhausted = True
            reply = text_reply("Is there anything else I can help you with?")
        self.prompt_tokens += int(reply.usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(reply.usage.get("completion_tokens") or 0)
        return reply

    def stats(self) -> dict[str, Any]:
        row = {"requests": len(self.requests), "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens, "cached_tokens": 0}
        return {
            "model": self.model, "provider": self.provider, "requests": len(self.requests), "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": 0, "completion_tokens": self.completion_tokens, "fallbacks": 0, "by_model": {LLM_KEY: row},
        }

    async def aclose(self) -> None:
        self.closed = True


class FakeSTT:
    """One call's transcription stream; the test speaks for the caller with ``caller_says``."""

    name = "deepgram"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.events_in: asyncio.Queue[STTEvent] = asyncio.Queue()
        self.audio_frames = 0
        self._connected = False
        self.closed = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def send_audio_b64(self, payload: str) -> None:
        self.audio_frames += 1

    async def clear_input(self) -> None:
        return None

    async def events(self):  # noqa: ANN201
        while True:
            event = await self.events_in.get()
            yield event
            if event.type == "closed":
                return

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            await self.events_in.put(STTEvent("closed"))

    def usage(self) -> dict[str, Any]:
        return {"provider": "deepgram", "model": "nova-3", "audio_seconds": round(self.audio_frames * 0.02, 2)}

    async def caller_says(self, text: str, item_id: str = "u") -> None:
        await self.events_in.put(STTEvent("speech_started", item_id=item_id))
        await self.events_in.put(STTEvent("speech_stopped", item_id=item_id))
        await self.events_in.put(STTEvent("completed", text=text, item_id=item_id))


class FakeTTS:
    name = "azure"

    def __init__(self) -> None:
        self.synthesized: list[str] = []
        self.warmed = 0

    async def synthesize_ex(self, text: str, *, language=None, persona=None, voice=None) -> tuple[bytes, str, str]:  # noqa: ANN001
        self.synthesized.append(text)
        return FAKE_AUDIO, "azure", "synth"

    async def synthesize(self, text: str, *, language=None, persona=None, voice=None) -> bytes:  # noqa: ANN001
        self.synthesized.append(text)
        return FAKE_AUDIO

    async def warm(self, lines, *, language=None, persona=None, voice=None) -> int:  # noqa: ANN001
        self.warmed += len(list(lines))
        return 0

    def is_cached(self, text: str, **_: Any) -> bool:
        return False

    def pin_lines(self, lines, **_: Any) -> int:  # noqa: ANN001
        return 0

    def stats(self) -> dict[str, Any]:
        return {"synth_count": len(self.synthesized)}

    async def aclose(self) -> None:
        return None


@dataclass
class FakeProviders:
    """What the engine gets instead of real providers; scripts are queued per conversation."""

    tts: FakeTTS = field(default_factory=FakeTTS)
    scripts: list[list[LLMReply]] = field(default_factory=list)
    llms: list[ScriptedLLM] = field(default_factory=list)
    stts: list[FakeSTT] = field(default_factory=list)

    def script(self, *replies: LLMReply) -> None:
        """The replies of the NEXT conversation's model (one script per call / chat)."""
        self.scripts.append(list(replies))

    def _llm(self, **kwargs: Any) -> ScriptedLLM:
        llm = ScriptedLLM(self.scripts.pop(0) if self.scripts else [], **kwargs)
        self.llms.append(llm)
        return llm

    async def _open_stt(self, **kwargs: Any) -> FakeSTT:
        stt = FakeSTT(**kwargs)
        await stt.connect()
        self.stts.append(stt)
        return stt

    def install(self, monkeypatch: Any) -> None:
        from app.voice import prepared, text_session, tts
        from app.voice.bridge import lifecycle, speaker, stt_loop
        from app.voice.providers import llm as llm_pkg
        from app.voice.providers import stt as stt_pkg
        from app.voice.providers import tts as tts_pkg

        def yes(*_: Any, **__: Any) -> bool:
            return True

        def get_tts_for(*_: Any, **__: Any) -> FakeTTS:
            return self.tts

        for module in (lifecycle, llm_pkg):
            monkeypatch.setattr(module, "llm_configured", yes)
            monkeypatch.setattr(module, "llm_for_call", self._llm)
        monkeypatch.setattr(text_session, "llm_for_call", self._llm)
        for module in (lifecycle, stt_pkg):
            monkeypatch.setattr(module, "stt_available", yes)
        for module in (lifecycle, tts_pkg, tts):
            monkeypatch.setattr(module, "tts_available", yes)
        monkeypatch.setattr(tts, "tts_configured", yes)
        monkeypatch.setattr(tts, "get_tts", lambda: self.tts)
        for module in (speaker, tts_pkg, tts):
            monkeypatch.setattr(module, "get_tts_for", get_tts_for)
        for module in (stt_loop, stt_pkg):
            monkeypatch.setattr(module, "open_stt", self._open_stt)
        assert prepared  # composed lines import the patched package attributes lazily


class WebhookReceiver:
    """The business's own endpoint (a MockTransport behind the outbound guard)."""

    #: What the receiver's host name "resolves" to (TEST-NET would be refused as non-public).
    PUBLIC_IP = "93.184.216.34"

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.errors: list[str] = []
        self.status = 200
        self.received = asyncio.Event()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.received.set()
        return httpx.Response(self.status, json={"ok": True})

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]


__all__ = ["FAKE_AUDIO", "FakeProviders", "FakeSTT", "FakeTTS", "ScriptedLLM", "WebhookReceiver", "text_reply", "tool_reply"]
