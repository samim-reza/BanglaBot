"""Bootstrap and teardown: provider checks, greeting-first start, task supervision,
the forwarded-call shortcut, and the final transcript / usage write."""

from __future__ import annotations

import asyncio
import time

import structlog

from app.core.regions import region_of
from app.flows.base import OUTCOME_DIVERTED
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.services import concurrency, live_calls
from app.voice import prepared
from app.voice.providers.llm import llm_configured, llm_for_call
from app.voice.providers.stt import stt_available
from app.voice.providers.tts import tts_available

logger = structlog.get_logger(__name__)


class LifecycleMixin:
    """``run`` and everything around it. Mixed into :class:`~app.voice.bridge.core.CallBridge`."""

    async def run(self) -> None:
        try:
            if not llm_configured(self.merchant):
                await logger.awarning("bridge_missing_llm_provider", call_log_id=self.call_log_id)
                await self._safe_close(code=1011)
                return
            if not stt_available(self.primary_language) or not tts_available(self.primary_language):
                await logger.awarning("bridge_missing_speech_provider", call_log_id=self.call_log_id, language=self.primary_language)
                await self._safe_close(code=1011)
                return
            tasks: list[asyncio.Task[None]] = []
            live_calls.register(self)
            # Holds this call's slot under the plan's simultaneous-call limit (idempotent: the
            # inbound webhook / outbound dialer already took it under the same call id).
            await concurrency.acquire(self.merchant, self.call_log_id)
            try:
                self.agent.settings = self.settings
                self._refresh_prepared()
                opening = self.agent.configure()
                self._llm = llm_for_call(flow_key=self.flow.key, merchant=self.merchant, channel="voice")
                self.agent.llm = self._llm
                # Greet FIRST — the opening is already in the TTS cache — and open the
                # transcription socket while it plays. The caller must hear a voice
                # within a second of answering; nothing else is allowed in front of it.
                self._turn_started_at = time.monotonic()
                self._turn_first_audio_logged = False
                self._speaker_task = asyncio.create_task(self._speaker_loop())
                self.speak(opening, allow_barge_in=False, message_ref=self.messages[-1])
                media_task = asyncio.create_task(self._media_loop())
                stt_connect = asyncio.create_task(self._connect_stt())
                asyncio.create_task(self._warm_tts_cache())
                if self.settings.voice_hangup_on_forwarded and self.call_sid and self.ctx.direction == DIRECTION_OUTBOUND:
                    asyncio.create_task(self._check_diverted())
                await stt_connect
                logger.info(
                    "bridge_stt_connected",
                    call_log_id=self.call_log_id,
                    provider=getattr(self._stt, "name", ""),
                    ms=int((time.monotonic() - self._turn_started_at) * 1000),
                )
                await self._emit_state()
                tasks = [
                    media_task,
                    asyncio.create_task(self._stt_loop()),
                    asyncio.create_task(self._watchdog()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                self.closed = True
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    if not task.cancelled() and task.exception() is not None:
                        raise task.exception()  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001
                await logger.awarning("bridge_failed", call_log_id=self.call_log_id, error=str(exc), error_type=type(exc).__name__)
                await self._safe_close()
        finally:
            live_calls.unregister(self.call_log_id)
            await concurrency.release(self.merchant, self.call_log_id)
            await self._teardown()

    def _refresh_prepared(self) -> None:
        """Lines composed while the phone rang (outbound) — picked up as soon as they exist."""
        record_id = str(getattr(self.order, "id", "") or "")
        if not record_id:
            return
        line = prepared.get_decision_line(record_id, self.primary_language)
        if line:
            self.ctx.prepared["decision"] = line

    async def _check_diverted(self) -> None:
        """Hang up when the carrier forwarded the call (reject → voicemail / divert).

        A rejected or busy callee is often forwarded by the network to a voicemail
        or "call back" service that answers as if it were a person; the provider marks
        such calls with ``forwarded_from`` (Telnyx doesn't report it, so this is a no-op there). Talking to it wastes minutes, so the
        call is dropped right away and the record goes back to ``no_answer``.
        """
        from app.services.call_service import fetch_call_details

        try:
            details = await fetch_call_details(self.call_sid)
        except Exception as exc:  # noqa: BLE001 — a lookup failure just means no shortcut
            await logger.ainfo("call_lookup_failed", call_log_id=self.call_log_id, error=str(exc))
            return
        forwarded = str(details.get("forwarded_from") or "").strip()
        if not forwarded or self.closed:
            return
        # Some carriers stamp forwarded_from with the dialed number itself on
        # ordinary answered calls; only a forward to a DIFFERENT number is a divert.
        from app.core.regions import normalize_phone

        region = region_of(self.merchant)
        dialed = normalize_phone(str(getattr(self.order, "customer_phone", "") or ""), region)
        if not dialed or normalize_phone(forwarded, region) == dialed:
            return
        await logger.ainfo(
            "call_diverted_hangup",
            call_log_id=self.call_log_id,
            forwarded_from=forwarded,
            answered_by=details.get("answered_by"),
        )
        self.closing = True
        await self._interrupt_playback("diverted")
        await self.agent.abandon(OUTCOME_DIVERTED)
        await self._safe_close()

    async def _teardown(self) -> None:
        self.closed = True
        for task in (self._pending_user_turn_task, self._speaker_task, self._agent_turn_task, self._agent_handle_task):
            if task and not task.done():
                task.cancel()
        if self._stt is not None:
            await self._close_stt(self._stt)
            self._retire_stt(self._stt)
        await self._finalize()
        if self._llm is not None:
            await self._llm.aclose()

    async def _finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        prepared.mark_call_ended(self.call_log_id)
        try:
            if not self.outcome and self.ctx.direction == DIRECTION_INBOUND:
                # The caller hung up first: keep what they told us when the flow can
                # use it (a partial lead), otherwise it was an enquiry.
                await self.agent.tools.finish_inbound()
            await self._persist_transcript(force=True)
            counters = {
                "tts_chars": self.tts_chars,
                "tts_cache_hits": self.tts_cache_hits,
                "duration_secs": int(time.monotonic() - self.started_at),
            }
            if self._llm is not None:
                counters["llm_prompt_tokens"] = int(self._llm.prompt_tokens)
                counters["llm_completion_tokens"] = int(self._llm.completion_tokens)
                counters["llm_cached_tokens"] = int(self._llm.cached_prompt_tokens)
            await self.store.save_usage(
                **counters,
                llm_stats=self._llm.stats() if self._llm is not None else None,
                stt_usage=list(self._stt_usage),
                tts_usage={"providers": self._tts_usage},
            )
            notify = getattr(self.store, "notify_finished", None)
            if notify is not None:
                await notify()
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("bridge_finalize_failed", call_log_id=self.call_log_id, error=str(exc))
        await logger.ainfo(
            "call_finished",
            call_log_id=self.call_log_id,
            flow=self.flow.key,
            outcome=self.outcome,
            final_node=self.runtime.current_node,
            duration_seconds=int(time.monotonic() - self.started_at),
            turns=self.agent.turns,
            fast_turns=self.agent.fast_turns,
            stt=self._stt_usage,
            llm=self._llm.stats() if self._llm is not None else {},
        )
