"""Fakes that drive ``CallBridge`` end to end — no network, no database.

* ``TelnyxSocket`` — the media websocket in Telnyx's shape (``start`` with
  ``call_control_id`` / ``stream_id``; ``media`` with ``track`` / ``chunk`` /
  ``timestamp`` / ``payload``; ``mark`` echoed back once "played"; ``stop``).
* ``ScriptedSTT`` — an STT session whose events the test pushes (``speech_started``,
  ``delta``, ``speech_stopped``, ``completed``, a drop or a broken stream) and which
  records the caller audio it was sent.
* ``ScriptedLLM`` — one scripted step per request: a reply, an exception, a slow
  reply (``Slow``) or a request that never returns (``HANG``).
* ``FakeTTS`` — μ-law audio for any line; can fail or hang per line.

The call harness that wires them into a ``CallBridge`` is :mod:`tests.bridge_harness`.
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.voice.llm import LLMReply, LLMToolCall
from app.voice.stt import STTEvent
from app.voice.tts import TTSError

SILENT_FRAME = base64.b64encode(b"\xff" * 160).decode("ascii")
LOUD_FRAME = base64.b64encode(b"\x00\x80" * 80).decode("ascii")


async def wait_until(predicate: Callable[[], Any], *, timeout: float = 5.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def reply(content: str = "", tool_calls: list[LLMToolCall] | None = None) -> LLMReply:
    return LLMReply(content=content, tool_calls=tool_calls or [], usage={}, assistant_message={}, finish_reason="stop")


def tool(call_id: str, name: str, arguments: str = "{}") -> LLMToolCall:
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


# ---------------------------------------------------------------------- media socket
class TelnyxSocket:
    def __init__(self, *, auto_mark: bool = True) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.closed = False
        self.auto_mark = auto_mark
        self.log: list[str] = []  # "phone" / "socket" ordering, shared with the call-control fake
        self._seq = itertools.count(1)
        self._chunk = itertools.count(1)
        self._played_until = 0.0  # Telnyx's playout clock: 20 ms per media frame received

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)
        event = message.get("event")
        if event == "media":
            self._played_until = max(time.monotonic(), self._played_until) + 0.02
        elif event == "clear":
            self._played_until = time.monotonic()
        elif event == "mark" and self.auto_mark:
            # Like Telnyx: the mark comes back once the audio queued before it has played.
            asyncio.get_running_loop().call_later(max(0.0, self._played_until - time.monotonic()), self._echo_mark, message["mark"]["name"])

    def _echo_mark(self, name: str) -> None:
        self.inbound.put_nowait({"event": "mark", "sequence_number": str(next(self._seq)), "mark": {"name": name}, "stream_id": "st-1"})

    async def receive_json(self) -> dict[str, Any]:
        return await self.inbound.get()

    async def close(self, code: int | None = None) -> None:
        self.closed = True
        self.log.append("socket")
        await self.inbound.put({"event": "stop"})

    def start(self, call_control_id: str = "v3:call-1") -> None:
        self.inbound.put_nowait(
            {
                "event": "start",
                "sequence_number": str(next(self._seq)),
                "start": {"call_control_id": call_control_id, "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}},
                "stream_id": "st-1",
            }
        )

    async def media(self, payload: str, count: int = 1, *, pace: float = 0.001) -> None:
        for _ in range(count):
            chunk = next(self._chunk)
            await self.inbound.put(
                {
                    "event": "media",
                    "sequence_number": str(next(self._seq)),
                    "media": {"track": "inbound", "chunk": str(chunk), "timestamp": str(chunk * 20), "payload": payload},
                    "stream_id": "st-1",
                }
            )
            await asyncio.sleep(pace)

    def media_payloads(self) -> list[str]:
        return [m["media"]["payload"] for m in self.sent if m.get("event") == "media"]

    def clears(self) -> int:
        return sum(1 for m in self.sent if m.get("event") == "clear")


# ----------------------------------------------------------------------------- STT
class ScriptedSTT:
    instances: list["ScriptedSTT"] = []

    def __init__(self, name: str = "fake", **kwargs: Any) -> None:
        self.name = name
        self.kwargs = kwargs
        self.events_in: asyncio.Queue[STTEvent | BaseException] = asyncio.Queue()
        self.audio: list[str] = []
        self.connected = False
        self.closed = False
        ScriptedSTT.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def send_audio_b64(self, payload: str) -> None:
        self.audio.append(payload)

    async def clear_input(self) -> None:
        return None

    async def events(self):
        while True:
            item = await self.events_in.get()
            if isinstance(item, BaseException):
                raise item
            yield item
            if item.type == "closed":
                return

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.connected = False
            await self.events_in.put(STTEvent("closed"))

    def usage(self) -> dict[str, Any]:
        return {"provider": self.name, "model": "fake", "audio_seconds": round(len(self.audio) * 0.02, 2)}

    # --- scripting ---
    def push(self, kind: str, text: str = "") -> None:
        self.events_in.put_nowait(STTEvent(kind, text=text))

    async def says(self, text: str) -> None:
        """One utterance the way Deepgram reports it: start, interim words, end, final."""
        self.push("speech_started")
        words = text.split()
        for size in range(min(4, len(words)), len(words), 6):
            self.push("delta", " ".join(words[:size]))
            await asyncio.sleep(0.005)
        self.push("speech_stopped")
        self.push("completed", text)
        await asyncio.sleep(0.01)

    def drop(self) -> None:
        """The provider closed the socket mid-call."""
        self.connected = False
        self.push("closed", "socket dropped")

    def break_stream(self, exc: BaseException) -> None:
        self.connected = False
        self.events_in.put_nowait(exc)


# ----------------------------------------------------------------------------- LLM
@dataclass
class Slow:
    seconds: float
    step: Any


HANG = object()


class ScriptedLLM:
    def __init__(self, script: list[Any], *, default: Callable[[], Any] | None = None, **kwargs: Any) -> None:
        self.script = list(script)
        self.default = default
        self.calls: list[list[dict[str, Any]]] = []
        self.cancelled = 0
        self.prompt_tokens = self.completion_tokens = self.cached_prompt_tokens = 0
        self.closed = False

    async def complete(self, messages, *, tools=None, tool_choice="auto", temperature=None) -> LLMReply:
        self.calls.append([dict(m) for m in messages])
        if self.script:
            step = self.script.pop(0)
        elif self.default is not None:
            step = self.default()
        else:
            raise AssertionError("ScriptedLLM ran out of steps")
        try:
            while isinstance(step, Slow):
                await asyncio.sleep(step.seconds)
                step = step.step
            if step is HANG:
                await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        if isinstance(step, BaseException):
            raise step
        return step

    def user_messages(self, call: int = -1) -> list[str]:
        return [m["content"] for m in self.calls[call] if m.get("role") == "user"]

    def stats(self) -> dict[str, Any]:
        return {"requests": len(self.calls)}

    async def aclose(self) -> None:
        self.closed = True


# ----------------------------------------------------------------------------- TTS
def seconds_of_audio(seconds: float) -> bytes:
    return b"\x10" * int(8000 * seconds)


class FakeTTS:
    def __init__(
        self,
        audio: bytes = b"\x10" * 480,
        *,
        audio_for: Callable[[str], bytes | None] | None = None,
        fail: Callable[[str], bool] | None = None,
        hang: Callable[[str], bool] | None = None,
    ) -> None:
        self.audio = audio
        self.audio_for = audio_for or (lambda text: None)
        self.fail = fail or (lambda text: False)
        self.hang = hang or (lambda text: False)
        self.synthesized: list[str] = []

    async def synthesize(self, text: str, *, language=None, persona=None, voice=None) -> bytes:
        self.synthesized.append(text)
        if self.hang(text):
            await asyncio.Event().wait()
        if self.fail(text):
            raise TTSError("all TTS providers failed: fake")
        return self.audio_for(text) or self.audio

    async def warm(self, lines, *, language, persona, voice=None) -> int:
        return 0

    def stats(self) -> dict[str, Any]:
        return {"synth_count": len(self.synthesized)}
