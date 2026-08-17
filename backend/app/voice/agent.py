"""Pipecat voice pipeline for one Twilio Media Streams call.

Twilio connects a websocket per call; we run STT -> LLM -> TTS over it,
entirely in Bengali, and save the transcript when the call ends.
"""

from fastapi import WebSocket
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.worker import PipelineParams
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import CallLog, Merchant, Order, OrderStatus
from app.voice import behavior
from app.voice.prompts import build_system_prompt, opening_greeting
from app.voice.tools import CallAgentTools, tool_schemas
from app.voice.tts import create_tts_service


def _transcript_from_context(context: LLMContext) -> str:
    lines = []
    for msg in context.get_messages():
        role, content = msg.get("role"), msg.get("content")
        if role not in ("user", "assistant") or not content:
            continue
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        if str(content).strip():
            speaker = "কাস্টমার" if role == "user" else "এজেন্ট"
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


async def run_call_agent(websocket: WebSocket) -> None:
    settings = get_settings()
    _, call_data = await parse_telephony_websocket(websocket)
    stream_sid = call_data["stream_id"]
    call_sid = call_data["call_id"]
    order_id = call_data.get("body", {}).get("order_id", "")

    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        merchant = await db.get(Merchant, order.merchant_id) if order else None
    if not order or not merchant:
        logger.error(f"No order/merchant for stream (order_id={order_id!r}); closing")
        await websocket.close()
        return

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,  # enables auto hang-up when the task ends
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    stt = OpenAISTTService(
        api_key=settings.openai_api_key,
        model=settings.openai_stt_model,
        language=Language.BN,
    )
    tts = create_tts_service(merchant.voice_tier)
    llm = OpenAILLMService(api_key=settings.openai_api_key, model=settings.openai_llm_model)

    tools = CallAgentTools(order_id=order.id, call_sid=call_sid, support_phone=merchant.support_phone)
    tools.register(llm)

    context = LLMContext(
        messages=[{"role": "system", "content": build_system_prompt(order, merchant)}],
        tools=tool_schemas(),
    )
    # Merchant-tunable call behavior (defaults in app/voice/behavior.py):
    # noise_mode = VAD strictness, barge_in_mode = when the caller may
    # interrupt, silence_hangup_secs = auto-drop after caller silence.
    idle_secs = behavior.silence_hangup_secs(merchant.silence_hangup_secs)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=behavior.vad_params(merchant.noise_mode)),
            user_turn_strategies=behavior.turn_strategies(merchant.barge_in_mode),
            user_idle_timeout=idle_secs,
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
        idle_timeout_secs=90,
    )

    @user_aggregator.event_handler("on_user_turn_idle")
    async def on_user_idle(aggregator):
        # Caller said nothing for idle_secs after the agent finished speaking:
        # mark the call auto-dropped (order becomes callable again) and hang up.
        logger.info(f"Call {call_sid}: caller silent for {idle_secs}s — auto-dropping")
        await _mark_auto_dropped(call_sid, order.id)
        await task.queue_frames(
            [TTSSpeakFrame("আপনাকে শুনতে পাচ্ছি না, তাই কলটি রাখছি। পরে আবার কল করা হবে, ধন্যবাদ।")]
        )
        await task.stop_when_done()

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Call {call_sid} connected for order {order.id}")
        # Speak the greeting with the selected TTS (not Twilio <Say>), then let
        # the LLM continue. TTS pauses inbound frames so the two don't overlap.
        await task.queue_frames(
            [TTSSpeakFrame(opening_greeting(merchant)), LLMRunFrame()]
        )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Call {call_sid} disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    finally:
        await _save_transcript(call_sid, _transcript_from_context(context))


async def _mark_auto_dropped(call_sid: str, order_id: str) -> None:
    """Record the silent-caller drop: outcome "auto_dropped" on the log and the
    order back to no_answer so it can be called again. A real outcome recorded
    earlier in the call (confirm/cancel) always wins."""
    async with AsyncSessionLocal() as db:
        log = (
            await db.execute(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
        ).scalar_one_or_none()
        if log and not log.outcome:
            log.outcome = "auto_dropped"
            order = await db.get(Order, order_id)
            if order and order.status == OrderStatus.calling:
                order.status = OrderStatus.no_answer
            await db.commit()


async def _save_transcript(call_sid: str, transcript: str) -> None:
    if not transcript:
        return
    async with AsyncSessionLocal() as db:
        log = (
            await db.execute(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
        ).scalar_one_or_none()
        if log:
            log.transcript = transcript
            await db.commit()
