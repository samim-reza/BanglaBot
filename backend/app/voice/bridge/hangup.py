"""Ending the call: hangup after the goodbye has played, transfer to the business's
support line (or to emergency help), ending the phone leg and closing the media socket."""

from __future__ import annotations

import asyncio

import structlog

from app.core.regions import region_of
from app.voice import emergency_dial, prepared
from app.voice.bridge.utterance import _Utterance
from app.voice.languages import phrase

logger = structlog.get_logger(__name__)


class HangupMixin:
    """Goodbye / transfer / close. Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    def _schedule_hangup(self, utterance: _Utterance | None) -> None:
        if self._hangup_scheduled:
            return
        self._hangup_scheduled = True
        asyncio.create_task(self._close_after_goodbye(utterance))

    async def _close_after_goodbye(self, utterance: _Utterance | None) -> None:
        if utterance is not None:
            try:
                await asyncio.wait_for(utterance.done.wait(), timeout=self._goodbye_hangup_delay_seconds + 5.0)
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(self._goodbye_playback_tail_seconds)
        if not self.closed:
            await self._emit({"event": "hangup", **self.agent.state()})
            await self._safe_close()

    async def _transfer_call(self, number: str) -> None:
        """Dial the business's support line (or emergency help) once the transfer line has played."""
        emergency, number = emergency_dial.unmark(number)
        await asyncio.sleep(0.3)
        try:
            ok = await (self._dial_emergency(number) if emergency else self._dial_support(number))
        except Exception as exc:  # noqa: BLE001
            ok = False
            await logger.awarning("transfer_dial_failed", call_log_id=self.call_log_id, error=str(exc))
        if ok:
            await logger.ainfo("transfer_started", call_log_id=self.call_log_id, target=number)
            # Telnyx ends the stream when the call moves to <Dial>; close our side too.
            await asyncio.sleep(2.0)
            await self._safe_close(end_phone_call=False)
            return
        if emergency:
            line = phrase("emergency_not_connected", self.active_language, emergency=self._emergency_words())
        else:
            line = phrase("closing_transfer_callback", self.active_language)
        self.messages.append({"role": "assistant", "content": line})
        self.speak(line, allow_barge_in=False, close_after=True)

    async def _dial_support(self, number: str) -> bool:
        from app.services import telnyx
        from app.services.call_service import redirect_call_to_human

        if not self.call_sid or self.web:
            return False
        return await redirect_call_to_human(self.call_sid, number, region_of(self.merchant), caller_id=telnyx.number_for(self.merchant))

    def _emergency_words(self) -> str:
        return self.ctx.say_number(self.ctx.emergency_number, self.active_language)

    async def _dial_emergency(self, number: str) -> bool:
        from app.services import telnyx
        from app.services.call_service import redirect_call_to_emergency

        if not self.call_sid or self.web:
            return False
        after = phrase("emergency_after_dial", self.active_language, emergency=self._emergency_words())
        return await redirect_call_to_emergency(
            self.call_sid, number, region_of(self.merchant), caller_id=telnyx.number_for(self.merchant), after=after
        )

    async def _end_phone_call(self) -> None:
        if not self.call_sid or self.web:
            return
        from app.services.call_service import complete_call

        try:
            await complete_call(self.call_sid)
        except Exception as exc:  # noqa: BLE001
            await logger.ainfo("complete_call_failed", call_log_id=self.call_log_id, error=str(exc))

    async def _safe_close(self, *, code: int | None = None, end_phone_call: bool = True) -> None:
        self._closed_by_agent = True
        already_closed = self.closed
        self.closed = True
        prepared.mark_call_ended(self.call_log_id)
        # End the phone leg before closing the socket: Telnyx re-opens a media stream that
        # drops while the call is still up, which would start the conversation over.
        if end_phone_call and not already_closed:
            await self._end_phone_call()
        try:
            if code is not None:
                await self.websocket.close(code=code)
            else:
                await self.websocket.close()
        except Exception:  # noqa: BLE001
            pass
