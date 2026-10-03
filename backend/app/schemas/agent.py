from typing import Any

from pydantic import BaseModel, Field


class TestCallStart(BaseModel):
    """Open a test conversation from the portal."""

    #: inbound = the customer calls/chats the business; outbound = the business calls a record.
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    record_id: str | None = None
    #: Pretend caller ID (inbound): finds that caller's appointments / bookings.
    caller_number: str = Field(default="", max_length=32)


class TestCallTicket(BaseModel):
    call_log_id: str
    #: The record of an outbound test call ("" for inbound).
    order_id: str = ""
    media_token: str
    #: Public wss:// URL when PUBLIC_BASE_URL is set; the console falls back to the backend host.
    ws_url: str | None = None
    stream_sid: str


class ChatStartResponse(BaseModel):
    session_id: str
    messages: list[str]
    state: dict[str, Any]


class ChatSay(BaseModel):
    text: str = Field(min_length=1, max_length=600)


class ChatReply(BaseModel):
    messages: list[str]
    ended: bool
    state: dict[str, Any] = {}
