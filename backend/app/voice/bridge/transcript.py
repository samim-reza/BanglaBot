"""The call transcript (kept in memory, saved every few turns and at the end) and the
extra events the browser test console gets (``transcript`` / ``state``)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Persist the transcript every N caller turns (and always at the end).
TRANSCRIPT_SAVE_EVERY = 3


class TranscriptMixin:
    """Transcript keeping and console events. Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    def _record_assistant_transcript(self, text: str) -> None:
        text = " ".join(str(text or "").split())
        if not text:
            return
        if self.transcript_lines and self.transcript_lines[-1] == ("Agent", text):
            return
        self.transcript_lines.append(("Agent", text))
        if self.web:
            asyncio.create_task(self._emit({"event": "transcript", "role": "agent", "text": text}))

    def transcript_text(self) -> str:
        return "\n".join(f"{role}: {text}" for role, text in self.transcript_lines)

    async def _persist_transcript(self, *, force: bool = False) -> None:
        if not force and self.agent.turns - self._transcript_saved_turns < TRANSCRIPT_SAVE_EVERY:
            return
        if not self.transcript_lines:
            return
        self._transcript_saved_turns = self.agent.turns
        try:
            await self.store.save_transcript(self.transcript_text(), language=self.active_language, final_node=self.runtime.current_node)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("transcript_persist_failed", call_log_id=self.call_log_id, error=str(exc))

    # ------------------------------------------------------------------ test console events
    async def _emit(self, message: dict[str, Any]) -> None:
        """Extra events for the browser test console (never sent to Telnyx)."""
        if not self.web or self.closed:
            return
        try:
            await self.websocket.send_json(message)
        except Exception:  # noqa: BLE001
            pass

    async def _emit_state(self) -> None:
        await self._emit({"event": "state", **self.agent.state()})
