"""Test the agent from the portal: a browser voice call, or a typed chat."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.config import get_settings
from app.core.security import sign_media_stream_token
from app.db.session import get_db
from app.flows.context import DIRECTION_INBOUND
from app.models import Merchant, Order
from app.schemas.agent import ChatReply, ChatSay, ChatStartResponse, TestCallStart, TestCallTicket
from app.services import call_service
from app.services.call_service import DbCallStore
from app.verticals import flow_for
from app.voice import prepared, text_session
from app.voice.twiml import PublicUrlMissing, stream_url

router = APIRouter(prefix="/api/agent", tags=["agent"])


async def _record(db: AsyncSession, merchant: Merchant, data: TestCallStart) -> Order | None:
    if data.direction == DIRECTION_INBOUND or not data.record_id:
        return None
    order = await db.get(Order, data.record_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Record not found")
    return order


def _require_keys(*, voice: bool) -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured on the server")
    if voice and not settings.azure_speech_key:
        raise HTTPException(status_code=503, detail="AZURE_SPEECH_KEY is not configured on the server")


@router.post("/test-call", response_model=TestCallTicket)
async def start_test_call(data: TestCallStart, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """A ticket for the browser test console: it opens the media websocket itself
    and speaks Twilio's media-stream protocol, so the call runs the production path."""
    _require_keys(voice=True)
    record = await _record(db, merchant, data)
    log, ctx = await call_service.open_test_call(
        db, merchant, direction=data.direction, record=record, caller_number=data.caller_number, mode="web"
    )
    prepared.put_call_snapshot(log.id, prepared.CallSnapshot(merchant=merchant, order=record, ctx=ctx, direction=data.direction, web=True))
    try:
        ws_url = stream_url()
    except PublicUrlMissing:
        ws_url = None
    return TestCallTicket(
        call_log_id=log.id,
        order_id=str(getattr(record, "id", "") or ""),
        media_token=sign_media_stream_token(order_id=str(getattr(record, "id", "") or ""), call_log_id=log.id),
        ws_url=ws_url,
        stream_sid=f"web-{secrets.token_hex(8)}",
    )


@router.post("/chat", response_model=ChatStartResponse)
async def start_chat(data: TestCallStart, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    _require_keys(voice=False)
    record = await _record(db, merchant, data)
    log, ctx = await call_service.open_test_call(
        db, merchant, direction=data.direction, record=record, caller_number=data.caller_number, mode="chat"
    )
    ctx.channel = "chat"
    store = DbCallStore(
        order_id=str(getattr(record, "id", "") or ""), call_log_id=log.id, merchant_id=merchant.id, currency=merchant.currency, source="test"
    )
    session = text_session.TextSession(
        merchant=merchant, ctx=ctx, flow=flow_for(merchant, data.direction), store=store, call_log_id=log.id
    )
    text_session.register(session)
    messages = await session.start()
    return ChatStartResponse(session_id=session.id, messages=messages, state=session.state())


def _session(session_id: str, merchant: Merchant) -> text_session.TextSession:
    session = text_session.get(session_id)
    if session is None or getattr(session.merchant, "id", None) != merchant.id:
        raise HTTPException(status_code=404, detail="This chat has ended — start a new one")
    return session


@router.post("/chat/{session_id}", response_model=ChatReply)
async def chat_say(session_id: str, data: ChatSay, merchant: Merchant = Depends(get_current_merchant)):
    session = _session(session_id, merchant)
    messages = await session.say(data.text)
    return ChatReply(messages=messages, ended=session.ended, state=session.state())


@router.post("/chat/{session_id}/end", response_model=ChatReply)
async def chat_end(session_id: str, merchant: Merchant = Depends(get_current_merchant)):
    session = _session(session_id, merchant)
    await session.finish()
    return ChatReply(messages=[], ended=True, state=session.state())
