"""Tool handlers the voice agent uses to record the call outcome.

Each handler writes to the DB immediately so the UI updates even if the
call later drops. The transfer tool redirects the live Twilio call to the
merchant's support number.
"""

import asyncio

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import EndTaskFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallParams

from app.db.session import AsyncSessionLocal
from app.models import CallLog, Order, OrderStatus
from app.services.call_service import normalize_bd_phone, twilio_client


def tool_schemas() -> ToolsSchema:
    no_args: dict = {}
    return ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name="confirm_order",
                description="কাস্টমার অর্ডারটি নিশ্চিত করলে এটি কল করো।",
                properties=no_args,
                required=[],
            ),
            FunctionSchema(
                name="cancel_order",
                description="কাস্টমার অর্ডারটি বাতিল করলে এটি কল করো।",
                properties={"reason": {"type": "string", "description": "বাতিলের কারণ (বাংলায়)"}},
                required=[],
            ),
            FunctionSchema(
                name="transfer_to_human",
                description="কাস্টমার মানুষের সাথে কথা বলতে চাইলে বা তুমি উত্তর দিতে না পারলে এটি কল করো।",
                properties=no_args,
                required=[],
            ),
            FunctionSchema(
                name="end_call",
                description="বিদায় জানানোর পরে কলটি শেষ করতে এটি কল করো।",
                properties=no_args,
                required=[],
            ),
        ]
    )


class CallAgentTools:
    """Closure over one call's order/merchant, registered on the LLM service."""

    def __init__(self, order_id: str, call_sid: str, support_phone: str):
        self.order_id = order_id
        self.call_sid = call_sid
        self.support_phone = support_phone
        self.outcome: str = ""

    def register(self, llm) -> None:
        # cancel_on_interruption=False: a customer talking over the agent must
        # never cancel the DB write that records the call outcome.
        llm.register_function("confirm_order", self.confirm_order, cancel_on_interruption=False)
        llm.register_function("cancel_order", self.cancel_order, cancel_on_interruption=False)
        llm.register_function(
            "transfer_to_human", self.transfer_to_human, cancel_on_interruption=False
        )
        llm.register_function("end_call", self.end_call, cancel_on_interruption=False)

    async def _set_outcome(self, status: OrderStatus, outcome: str, note: str = "") -> None:
        self.outcome = outcome
        async with AsyncSessionLocal() as db:
            order = await db.get(Order, self.order_id)
            if order:
                order.status = status
                if note:
                    order.notes = (order.notes + "\n" if order.notes else "") + note
            from sqlalchemy import select

            log = (
                await db.execute(
                    select(CallLog).where(CallLog.twilio_call_sid == self.call_sid)
                )
            ).scalar_one_or_none()
            if log:
                log.outcome = outcome
            await db.commit()
        logger.info(f"Order {self.order_id} outcome: {outcome}")

    async def confirm_order(self, params: FunctionCallParams):
        await self._set_outcome(OrderStatus.confirmed, "confirmed")
        await params.result_callback({"ok": True, "message": "অর্ডার নিশ্চিত করা হয়েছে।"})

    async def cancel_order(self, params: FunctionCallParams):
        reason = str(params.arguments.get("reason", "") or "")
        await self._set_outcome(
            OrderStatus.cancelled, "cancelled", f"বাতিলের কারণ: {reason}" if reason else ""
        )
        await params.result_callback({"ok": True, "message": "অর্ডার বাতিল করা হয়েছে।"})

    async def transfer_to_human(self, params: FunctionCallParams):
        await self._set_outcome(OrderStatus.needs_review, "transfer")
        if not self.support_phone:
            await params.result_callback(
                {
                    "ok": False,
                    "message": "এখন কাউকে সংযোগ দেওয়া যাচ্ছে না। বলো: একজন প্রতিনিধি শীঘ্রই কল করবেন। তারপর end_call করো।",
                }
            )
            return
        await params.llm.push_frame(
            TTSSpeakFrame("আপনাকে একজন প্রতিনিধির সাথে সংযোগ দেওয়া হচ্ছে, একটু লাইনে থাকুন।")
        )
        await params.result_callback({"ok": True, "message": "সংযোগ দেওয়া হচ্ছে।"})
        asyncio.create_task(self._delayed_transfer())

    async def _delayed_transfer(self) -> None:
        # Give the TTS a moment to finish before the media stream is replaced.
        await asyncio.sleep(5)
        try:
            number = normalize_bd_phone(self.support_phone)
            twiml = f'<Response><Dial timeout="25">{number}</Dial></Response>'
            twilio_client().calls(self.call_sid).update(twiml=twiml)
            logger.info(f"Call {self.call_sid} transferred to {number}")
        except Exception as e:
            logger.error(f"Transfer failed for {self.call_sid}: {e}")

    async def end_call(self, params: FunctionCallParams):
        await params.result_callback({"ok": True})
        await params.llm.push_frame(TTSSpeakFrame("ধন্যবাদ, ভালো থাকবেন।"))
        await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
