"""``WS /stt``: streaming speech-to-text for phone audio (Telnyx base64 mu-law 8 kHz frames)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .auth import websocket_key_ok
from .stream import SttStream
from .stt import check_language

log = logging.getLogger("speech.ws")
router = APIRouter()


async def _deny(websocket: WebSocket) -> None:
    """Reject the handshake with HTTP 401 when the server supports it, else close 4401."""
    try:
        await websocket.send_denial_response(JSONResponse({"detail": "missing or invalid X-Speech-Key"}, 401))
    except RuntimeError:
        await websocket.close(code=4401, reason="unauthorized")


def _silence_ms(raw: str | None, default: int) -> int:
    try:
        return max(150, min(5000, int(raw or default)))
    except ValueError:
        return default


@router.websocket("/stt")
async def stt_socket(websocket: WebSocket) -> None:
    if not websocket_key_ok(websocket):
        await _deny(websocket)
        return
    engines = websocket.app.state.engines
    await websocket.accept()
    send_lock = asyncio.Lock()

    async def send(message: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_text(json.dumps(message))

    params = websocket.query_params
    try:
        check_language(params.get("language"))
    except ValueError as exc:
        await send({"type": "error", "message": str(exc)})
        await websocket.close(code=1008, reason="unsupported language")
        return

    silence_ms = _silence_ms(params.get("silence_ms"), engines.settings.silence_ms)
    session = SttStream(engines, send, silence_ms=silence_ms)
    log.info("stt stream opened (silence_ms=%d)", silence_ms)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes"):
                await session.push_ulaw(message["bytes"])
            elif message.get("text") is not None:
                await _handle_text(session, message["text"], send)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.exception("stt stream failed")
        try:
            await send({"type": "error", "message": f"server error: {exc}"})
        except Exception:  # noqa: BLE001
            pass
    finally:
        await session.close()
        log.info("stt stream closed after %d utterances", session.utterances)


async def _handle_text(session: SttStream, raw: str, send: Any) -> None:
    try:
        data = json.loads(raw)
    except ValueError:
        await send({"type": "error", "message": "frames must be JSON"})
        return
    kind = data.get("type") if isinstance(data, dict) else None
    if kind == "audio":
        try:
            audio = base64.b64decode(data.get("audio") or "", validate=False)
        except (binascii.Error, ValueError):
            await send({"type": "error", "message": "audio is not valid base64"})
            return
        await session.push_ulaw(audio)
    elif kind == "clear":
        session.clear()
    else:
        await send({"type": "error", "message": f"unknown message type {kind!r}"})
