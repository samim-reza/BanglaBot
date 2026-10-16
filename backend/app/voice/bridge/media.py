"""Media socket in: the Telnyx / console event loop, inbound caller frames and
half-duplex gating (only sustained loud caller audio reaches the STT while the
agent speaks, and that same crossing interrupts playback)."""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import WebSocketDisconnect

from app.voice.audio import pcm_rms

logger = structlog.get_logger(__name__)

# Pre-roll kept ahead of the barge-in window while caller audio is gated (15 × 20 ms).
PREROLL_FRAMES = 15
# Caller audio kept while the STT (re)connects (250 × 20 ms = 5 s), sent once it is back.
STT_GAP_FRAMES = 250


class MediaMixin:
    """Reads the media websocket. Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    def _frame(self, event: str, **body: Any) -> dict[str, Any]:
        """An outgoing media-socket event: the console wants ``streamSid``; Telnyx
        rejects unknown fields."""
        message: dict[str, Any] = {"event": event, **body}
        if self.web:
            message["streamSid"] = self.stream_sid
        return message

    async def _media_loop(self) -> None:
        while not self.closed:
            try:
                message = await self.websocket.receive_json()
            except (WebSocketDisconnect, RuntimeError) as exc:
                if not self.closed:
                    await logger.ainfo("media_disconnected", call_log_id=self.call_log_id, detail=str(exc)[:120])
                self.closed = True
                await self._close_stt(self._stt)
                return
            event = message.get("event")
            if event == "start":
                start = message.get("start") or {}
                self.stream_sid = message.get("stream_id") or start.get("streamSid") or self.stream_sid
                self.call_sid = start.get("call_control_id") or start.get("callSid") or self.call_sid
            elif event == "media":
                payload = (message.get("media") or {}).get("payload") or ""
                if payload:
                    await self._handle_inbound_frame(payload)
            elif event == "mark":
                mark_name = str(((message.get("mark") or {}).get("name")) or "").strip()
                if mark_name and mark_name == self._pending_playback_mark:
                    self._pending_playback_mark = None
                    self._playback_mark_event.set()
            elif event == "error":
                await logger.awarning("media_stream_error", call_log_id=self.call_log_id, error=message.get("payload"))
            elif event == "stop":
                self.closed = True
                await self._close_stt(self._stt)
                break

    async def _to_stt(self, payload: str) -> None:
        """Forward one caller frame. While the STT is down or (re)connecting the last few
        seconds are kept and sent first once it is back, so words said in the gap still count."""
        stt = self._stt
        if stt is None or not getattr(stt, "connected", True):
            self._stt_gap.append(payload)
            return
        try:
            while self._stt_gap:
                await stt.send_audio_b64(self._stt_gap.popleft())
            await stt.send_audio_b64(payload)
        except Exception as exc:  # noqa: BLE001 — a broken STT socket must not end the call (the STT loop reconnects)
            if not self._stt_send_failed:
                self._stt_send_failed = True
                await logger.awarning("bridge_stt_send_failed", call_log_id=self.call_log_id, error=str(exc)[:160])

    async def _handle_inbound_frame(self, payload: str) -> None:
        rms = pcm_rms(payload)
        if not self.assistant_speaking:
            self._ambient_noise.update(rms)
        cap = 3200
        speech_gate = self._ambient_noise.gate(self.settings.voice_speech_start_min_rms, 2.0, cap)
        barge_gate = self._ambient_noise.gate(self.settings.voice_barge_in_min_rms, 2.5, cap)
        if rms >= speech_gate:
            self.last_customer_audio_at = time.monotonic()
            self.last_voice_activity_at = self.last_customer_audio_at
        if not self.assistant_speaking:
            self._barge_in_loud_frames = 0
            # Snapshot before awaiting: the speaker clears these buffers when a line starts.
            held = list(self._barge_in_prebuffer) if sum(self._barge_in_window) >= 2 else []
            self._barge_in_prebuffer.clear()
            self._barge_in_window.clear()
            for buffered in held:
                await self._to_stt(buffered)
            await self._to_stt(payload)
            return
        # Half duplex: only SUSTAINED loud audio (a real barge-in) reaches the STT;
        # everything else waits in the pre-roll buffer and is never billed.
        self._barge_in_window.append(1 if rms >= barge_gate else 0)
        self._barge_in_loud_frames = sum(self._barge_in_window)
        if self._barge_in_loud_frames < self.settings.voice_barge_in_min_frames:
            self._barge_in_prebuffer.append(payload)
            return
        self._barge_in_window.clear()
        held = list(self._barge_in_prebuffer)
        self._barge_in_prebuffer.clear()
        for buffered in held:
            await self._to_stt(buffered)
        await self._on_barge_in()
        await self._to_stt(payload)

    async def _on_barge_in(self) -> None:
        # Only the caller's words reset the silence count (a door slam is not an answer).
        self._last_barge_in_at = time.monotonic()
        if not self._barge_in_allowed:
            return
        await self._interrupt_playback("caller_barge_in")
