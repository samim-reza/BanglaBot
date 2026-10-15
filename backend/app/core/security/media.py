"""Media-stream tokens: carried in the TeXML ``<Stream>`` parameters, they tie one
websocket to one call (order + call log) for 15 minutes."""

from __future__ import annotations

from fastapi import HTTPException

from app.core.security.tokens import TYP_MEDIA_STREAM, sign_token, verify_token

MEDIA_STREAM_TOKEN_TTL_SECONDS = 15 * 60


def sign_media_stream_token(*, order_id: str, call_log_id: str, ttl_seconds: int = MEDIA_STREAM_TOKEN_TTL_SECONDS) -> str:
    return sign_token(
        {"order_id": str(order_id), "call_log_id": str(call_log_id)},
        ttl_seconds=ttl_seconds,
        typ=TYP_MEDIA_STREAM,
    )


def verify_media_stream_token(token: str, *, order_id: str, call_log_id: str) -> None:
    try:
        payload = verify_token(token, typ=TYP_MEDIA_STREAM)
    except HTTPException as exc:
        raise HTTPException(status_code=403, detail="Invalid media token") from exc
    if str(payload.get("order_id")) != str(order_id) or str(payload.get("call_log_id")) != str(call_log_id):
        raise HTTPException(status_code=403, detail="Media token does not match call")


__all__ = ["MEDIA_STREAM_TOKEN_TTL_SECONDS", "sign_media_stream_token", "verify_media_stream_token"]
