"""Telnyx's side of a call: the TeXML answer is parsed, then the media websocket is driven
straight through the ASGI app on the test's own event loop (``connected`` → ``start`` →
``media`` … → ``stop``), echoing every ``mark`` the way Telnyx does after playback."""

from __future__ import annotations

import asyncio
import base64
import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

SILENT_FRAME = base64.b64encode(b"\xff" * 160).decode("ascii")


@dataclass
class StreamAnswer:
    url: str
    parameters: dict[str, str]
    bidirectional_mode: str
    codec: str


def parse_stream(texml: str) -> StreamAnswer:
    """The ``<Connect><Stream>`` of an inbound answer (AssertionError when it isn't one)."""
    root = ET.fromstring(texml)
    stream = root.find("./Connect/Stream")
    assert stream is not None, f"no <Stream> in TeXML: {texml}"
    params = {node.get("name", ""): node.get("value", "") for node in stream.findall("Parameter")}
    return StreamAnswer(stream.get("url", ""), params, stream.get("bidirectionalMode", ""), stream.get("bidirectionalCodec", ""))


async def wait_until(predicate, *, timeout: float = 8.0, what: str = "condition") -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


class TelnyxMediaPeer:
    def __init__(self, app: Any, url: str, *, echo_marks: bool = True) -> None:
        parts = urlsplit(url)
        self.app = app
        self.path = parts.path or "/"
        self.echo_marks = echo_marks
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.received: list[dict[str, Any]] = []
        self.accepted = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_code: int | None = None
        self.task: asyncio.Task[None] | None = None
        self.stream_id = "e2e-stream-1"
        self._sequence = 0

    # ------------------------------------------------------------------ ASGI plumbing
    def _scope(self) -> dict[str, Any]:
        return {
            "type": "websocket", "asgi": {"version": "3.0", "spec_version": "2.3"}, "scheme": "ws", "http_version": "1.1",
            "path": self.path, "raw_path": self.path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"testserver"), (b"user-agent", b"telnyx-media/1")],
            "client": ("192.0.2.10", 40000), "server": ("testserver", 80), "subprotocols": [], "state": {},
        }

    async def _receive(self) -> dict[str, Any]:
        return await self.inbox.get()

    async def _send(self, message: dict[str, Any]) -> None:
        kind = message["type"]
        if kind == "websocket.accept":
            self.accepted.set()
        elif kind == "websocket.send":
            data = json.loads(message.get("text") or (message.get("bytes") or b"{}").decode())
            self.received.append(data)
            if self.echo_marks and data.get("event") == "mark" and not self.closed.is_set():
                await self.inbox.put({"type": "websocket.receive", "text": json.dumps({"event": "mark", "stream_id": self.stream_id, "mark": dict(data.get("mark") or {})})})
        elif kind == "websocket.close":
            self.close_code = int(message.get("code") or 1000)
            self.closed.set()
            await self.inbox.put({"type": "websocket.disconnect", "code": self.close_code})

    async def open(self) -> None:
        await self.inbox.put({"type": "websocket.connect"})
        self.task = asyncio.create_task(self.app(self._scope(), self._receive, self._send))
        done = asyncio.create_task(self.accepted.wait())
        try:
            await asyncio.wait_for(done, timeout=5.0)
        finally:
            done.cancel()

    async def _frame(self, event: str, **body: Any) -> None:
        self._sequence += 1
        frame = {"event": event, "sequence_number": str(self._sequence), "stream_id": self.stream_id, **body}
        await self.inbox.put({"type": "websocket.receive", "text": json.dumps(frame)})

    # ------------------------------------------------------------------ Telnyx frames
    async def start(self, parameters: dict[str, str], *, call_control_id: str = "v3:e2e-call", caller: str = "", called: str = "") -> None:
        await self.inbox.put({"type": "websocket.receive", "text": json.dumps({"event": "connected", "version": "1.0.0"})})
        await self._frame(
            "start",
            start={
                "user_id": "e2e-user", "call_control_id": call_control_id, "call_session_id": "e2e-session", "from": caller, "to": called,
                "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}, "custom_parameters": dict(parameters),
            },
        )

    async def media(self, count: int = 5, payload: str = SILENT_FRAME) -> None:
        for chunk in range(count):
            await self._frame("media", media={"track": "inbound", "chunk": str(chunk), "timestamp": str(chunk * 20), "payload": payload})
            await asyncio.sleep(0.002)

    async def stop(self) -> None:
        await self._frame("stop", stop={"user_id": "e2e-user", "call_control_id": "v3:e2e-call"})

    async def finished(self, timeout: float = 15.0) -> None:
        """Wait for the app's handler to return (the bridge tore the call down)."""
        assert self.task is not None
        await asyncio.wait_for(asyncio.shield(self.task), timeout=timeout)

    # ------------------------------------------------------------------ what Telnyx got back
    def audio_frames(self) -> int:
        return sum(1 for m in self.received if m.get("event") == "media")

    def marks(self) -> list[str]:
        return [str((m.get("mark") or {}).get("name")) for m in self.received if m.get("event") == "mark"]


__all__ = ["SILENT_FRAME", "StreamAnswer", "TelnyxMediaPeer", "parse_stream", "wait_until"]
