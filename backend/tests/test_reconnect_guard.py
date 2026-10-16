"""A finished call must not restart when Telnyx re-opens its media stream.

On 2026-10-15 a booked clinic call was followed 0.7 s later by a second stream for the
same call (the socket closed before the phone leg ended); the empty second session then
overwrote the call log with outcome "inquiry" and zero usage."""

from __future__ import annotations

from app.voice import prepared
from app.voice.bridge.hangup import HangupMixin


def test_ended_calls_are_remembered():
    prepared.clear()
    assert not prepared.call_ended("call-1")
    prepared.mark_call_ended("call-1")
    assert prepared.call_ended("call-1")
    prepared.clear()
    assert not prepared.call_ended("call-1")


class _Socket:
    def __init__(self, order: list[str]) -> None:
        self.order = order

    async def close(self, code: int | None = None) -> None:
        self.order.append("socket")


class _Bridge(HangupMixin):
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.closed = False
        self._closed_by_agent = False
        self.websocket = _Socket(order)
        self.call_log_id = "call-2"

    async def _end_phone_call(self) -> None:
        self.order.append("phone")


async def test_hangup_ends_the_phone_leg_before_closing_the_stream():
    prepared.clear()
    order: list[str] = []
    await _Bridge(order)._safe_close()
    assert order == ["phone", "socket"]
    assert prepared.call_ended("call-2")


async def test_closing_twice_hangs_up_once():
    order: list[str] = []
    bridge = _Bridge(order)
    await bridge._safe_close()
    await bridge._safe_close()
    assert order.count("phone") == 1


async def test_an_answered_call_whose_audio_never_connects_frees_its_line(monkeypatch):
    from app.services.calls import inbound

    released: list[str] = []

    async def release(merchant, call_id=None):  # noqa: ANN001, ANN202
        released.append(call_id)

    class _NoDb:
        async def __aenter__(self):  # noqa: ANN204
            raise RuntimeError("no database in unit tests")

        async def __aexit__(self, *exc):  # noqa: ANN002, ANN204
            return False

    monkeypatch.setattr(inbound.concurrency, "release", release)
    monkeypatch.setattr(inbound, "AsyncSessionLocal", lambda: _NoDb())
    prepared.clear()
    prepared.mark_media_started("connected")
    await inbound._release_if_no_media(object(), "connected", after=0)
    await inbound._release_if_no_media(object(), "silent", after=0)
    assert released == ["silent"]
