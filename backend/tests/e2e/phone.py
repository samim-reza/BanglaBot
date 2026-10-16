"""Placing an inbound phone call the way Telnyx does: the signed voice webhook, then the
media stream, with the fake STT speaking for the caller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from tests.e2e.fakes import FakeProviders, FakeSTT
from tests.e2e.telnyx_peer import StreamAnswer, TelnyxMediaPeer, parse_stream, wait_until


def booking_day(days_ahead: int = 3, tz: str = "America/New_York") -> str:
    from zoneinfo import ZoneInfo

    return (datetime.now(ZoneInfo(tz)) + timedelta(days=days_ahead)).date().isoformat()


def salon_booking(day: str, time_pref: str = "11:00", name: str = "Ana Lopez", *, staff: str = "T1") -> dict[str, Any]:
    """What a model would save from "a haircut with Maya on <day> at 11, I'm Ana Lopez"."""
    return {"intent": "book", "service": "S1", "staff": staff, "date": day, "time_pref": time_pref, "customer_name": name}


@dataclass
class PhoneCall:
    peer: TelnyxMediaPeer
    answer: StreamAnswer
    stt: FakeSTT
    call_sid: str

    @property
    def call_log_id(self) -> str:
        return self.answer.parameters["call_log_id"]

    def bridge(self) -> Any:
        from app.services import live_calls

        return live_calls._live.get(self.call_log_id)

    def agent_lines(self) -> list[str]:
        bridge = self.bridge()
        return [text for role, text in (bridge.transcript_lines if bridge is not None else []) if role == "Agent"]

    async def says(self, text: str, *, then_wait_for_lines: int | None = None) -> None:
        """The caller speaks (a few frames of audio, then the transcript); returns once the agent's
        real answer has played (an instant "Okay." acknowledgement alone doesn't count)."""
        from app.voice.languages import ack_lines

        acks = set(ack_lines("en"))
        before = len(self.agent_lines())
        await self.peer.media(5)
        await self.stt.caller_says(text)

        def answered() -> bool:
            lines = self.agent_lines()
            if then_wait_for_lines is not None:
                return len(lines) >= then_wait_for_lines
            return len(lines) > before and lines[-1] not in acks

        try:
            await wait_until(lambda: answered() or self.peer.closed.is_set(), what=f"the agent's answer to {text!r}")
        except AssertionError as exc:
            raise AssertionError(f"{exc}; agent said: {self.agent_lines()[before:]}") from exc

    async def wraps_up(self) -> None:
        """After the outcome: answer "anything else?" with no (when asked), then the agent hangs up."""
        bridge = self.bridge()
        if bridge is not None and not bridge.closing and not self.peer.closed.is_set():
            await self.says("No, that's all, thanks. Bye!")
        await self.hung_up_by_agent()

    async def hung_up_by_agent(self, timeout: float = 15.0) -> None:
        try:
            await self.peer.finished(timeout=timeout)
        except TimeoutError as exc:
            bridge = self.bridge()
            state = bridge.agent.state() if bridge is not None else {}
            raise AssertionError(f"the call did not end: lines={self.agent_lines()} state={state} closing={getattr(bridge, 'closing', None)}") from exc
        assert self.peer.closed.is_set(), "the agent never closed the media stream"


async def answer_inbound(client: httpx.AsyncClient, *, to: str, caller: str, call_sid: str, signed: bool = True) -> httpx.Response:
    from app.services import telnyx_urls

    path = urlsplit(telnyx_urls.inbound_url()).path if signed else "/telnyx/inbound"
    form = {"CallSid": call_sid, "AccountSid": "e2e-account", "From": caller, "To": to, "CallStatus": "ringing", "Direction": "inbound"}
    return await client.post(path, data=form)


async def dial(client: httpx.AsyncClient, app: Any, providers: FakeProviders, *, to: str, caller: str, call_sid: str) -> PhoneCall:
    """Answer an inbound call and connect its media stream; returns once the greeting has played."""
    response = await answer_inbound(client, to=to, caller=caller, call_sid=call_sid)
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/xml"), response.text
    answer = parse_stream(response.text)
    assert answer.url == "ws://testserver/telnyx/media" and answer.bidirectional_mode == "rtp" and answer.codec == "PCMU"
    sessions = len(providers.stts)
    peer = TelnyxMediaPeer(app, answer.url)
    await peer.open()
    await peer.start(answer.parameters, call_control_id=call_sid, caller=caller, called=to)
    await wait_until(lambda: len(providers.stts) > sessions, what="the STT session")
    call = PhoneCall(peer=peer, answer=answer, stt=providers.stts[-1], call_sid=call_sid)
    await wait_until(lambda: len(call.agent_lines()) >= 1, what="the greeting")
    return call


__all__ = ["PhoneCall", "answer_inbound", "booking_day", "dial", "salon_booking"]
