"""Text conversations on the same engine: the portal's chat test and the website widget.

A :class:`TextSession` is a :class:`~app.voice.agent.Speaker` whose "speech"
is a list of messages, so a typed conversation runs exactly the flow, tools,
fast paths and commits a phone call runs — bookings land in the records the
same way. Sessions live in memory (one backend process) and expire after
:data:`SESSION_TTL_SECONDS` of inactivity.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

import structlog

from app.core.config import get_settings
from app.flows.base import Flow
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.voice.agent import CallAgent
from app.voice.audio import clean_spoken_text
from app.voice.languages import normalize_language
from app.voice.llm import ChatLLM
from app.voice.tools import CallStore

logger = structlog.get_logger(__name__)

SESSION_TTL_SECONDS = 30 * 60
MAX_SESSIONS = 2000
MAX_MESSAGE_CHARS = 600


class TextSession:
    def __init__(
        self,
        *,
        merchant: Any,
        ctx: CallContext,
        flow: Flow,
        store: CallStore,
        call_log_id: str,
        settings: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self.id = secrets.token_urlsafe(18)
        self.merchant = merchant
        self.ctx = ctx
        self.flow = flow
        self.store = store
        self.call_log_id = call_log_id
        base = settings or get_settings()
        # No "Okay." filler in a chat: the reply arrives as one message.
        self.settings = base.model_copy(update={"voice_instant_ack": False}) if hasattr(base, "model_copy") else base
        self.language = normalize_language(getattr(merchant, "language", None))
        # Speaker protocol
        self.closed = False
        self.closing = False
        self.assistant_speaking = False
        self.ended = False
        self.outbox: list[str] = []
        self.transcript: list[tuple[str, str]] = []
        self.started_at = time.monotonic()
        self.last_used = self.started_at
        self._lock = asyncio.Lock()
        self._llm = llm
        self.agent = CallAgent(
            flow=flow,
            ctx=ctx,
            store=store,
            speaker=self,
            language=self.language,
            settings=self.settings,
            call_log_id=call_log_id,
            # A chat cannot be put through to a phone line: "a team member will call you back".
            support_phone="",
        )

    # ---- Speaker protocol ------------------------------------------------------
    def speak(
        self,
        text: str,
        *,
        allow_barge_in: bool = True,
        message_ref: dict[str, Any] | None = None,
        close_after: bool = False,
        transfer_to: str = "",
    ) -> None:
        text = clean_spoken_text(text)
        if text:
            self.outbox.append(text)
            self.transcript.append(("Agent", text))
        if close_after or transfer_to:
            self.ended = True

    def schedule_hangup(self) -> None:
        self.ended = True

    # ---- conversation ---------------------------------------------------------------
    async def start(self) -> list[str]:
        settings = self.settings
        if self._llm is None:
            self._llm = ChatLLM(
                api_key=str(settings.openai_api_key or ""),
                model=settings.openai_llm_model,
                reasoning_effort=settings.openai_llm_reasoning_effort,
                max_output_tokens=settings.openai_llm_max_output_tokens,
                prompt_cache_key=f"{self.flow.key}:chat:{getattr(self.merchant, 'id', '')}",
                prompt_cache_retention=settings.openai_prompt_cache_retention,
            )
        self.agent.llm = self._llm
        opening = self.agent.configure()
        self.speak(opening)
        return self._drain()

    async def say(self, text: str) -> list[str]:
        async with self._lock:
            self.last_used = time.monotonic()
            if self.ended:
                return []
            text = " ".join(str(text or "").split())[:MAX_MESSAGE_CHARS]
            if not text:
                return []
            self.transcript.append(("Customer", text))
            try:
                await self.agent.handle_turn(text)
            except Exception as exc:  # noqa: BLE001 — a chat must answer something
                await logger.awarning("text_session_turn_failed", session=self.id, error=str(exc), error_type=type(exc).__name__)
                from app.voice.languages import phrase

                self.speak(phrase("recovery", self.language))
            if self.ended:
                await self.finish()
            elif self.agent.turns % 3 == 0:
                await self._save_transcript()
            return self._drain()

    async def finish(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.ended = True
        try:
            if not self.agent.outcome and self.ctx.direction == DIRECTION_INBOUND:
                await self.agent.tools.finish_inbound()
            await self._save_transcript()
            counters = {"duration_secs": int(time.monotonic() - self.started_at)}
            if self._llm is not None:
                counters["llm_prompt_tokens"] = int(getattr(self._llm, "prompt_tokens", 0))
                counters["llm_completion_tokens"] = int(getattr(self._llm, "completion_tokens", 0))
                counters["llm_cached_tokens"] = int(getattr(self._llm, "cached_prompt_tokens", 0))
            await self.store.save_usage(**counters)
            notify = getattr(self.store, "notify_finished", None)
            if notify is not None:
                await notify()
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("text_session_finish_failed", session=self.id, error=str(exc))

    async def _save_transcript(self) -> None:
        if not self.transcript:
            return
        text = "\n".join(f"{role}: {line}" for role, line in self.transcript)
        try:
            await self.store.save_transcript(text, language=self.language, final_node=self.agent.runtime.current_node)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("text_session_transcript_failed", session=self.id, error=str(exc))

    def _drain(self) -> list[str]:
        out, self.outbox = self.outbox, []
        return out

    def state(self) -> dict[str, Any]:
        return {**self.agent.state(), "ended": self.ended}


# ------------------------------------------------------------------ in-process registry
_sessions: dict[str, TextSession] = {}


def register(session: TextSession) -> None:
    prune()
    if len(_sessions) >= MAX_SESSIONS:
        oldest = min(_sessions.values(), key=lambda s: s.last_used)
        _sessions.pop(oldest.id, None)
    _sessions[session.id] = session


def get(session_id: str) -> TextSession | None:
    session = _sessions.get(str(session_id or ""))
    if session is None or time.monotonic() - session.last_used > SESSION_TTL_SECONDS:
        return None
    return session


def prune() -> list[TextSession]:
    """Drop expired sessions; returns them so the caller can finish (persist) them."""
    now = time.monotonic()
    expired = [s for s in _sessions.values() if now - s.last_used > SESSION_TTL_SECONDS]
    for session in expired:
        _sessions.pop(session.id, None)
    return expired


async def reap() -> None:
    for session in prune():
        await session.finish()


__all__ = ["TextSession", "get", "prune", "reap", "register"]
