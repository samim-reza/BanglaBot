"""Tool handlers for the flow-driven voice agent.

Two families:
- save_details — the slot-filling tool. The model extracts whatever the
  caller said into structured fields; the flow runtime stores them,
  re-derives the current node (appending a "ধাপ পরিবর্তন" directive on a
  change) and returns the backend-owned wording of the next question.
- terminal tools (per service: confirm/cancel/reschedule/refuse) plus the
  shared transfer_to_human and end_call. Terminals write the outcome to the
  DB immediately so the UI updates even if the call later drops.
"""

import asyncio

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import EndTaskFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallParams
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.flows import Flow, FlowRuntime, Terminal
from app.models import CallLog, Order, OrderStatus
from app.services.call_service import normalize_bd_phone, twilio_client

AFTER_TERMINAL_MESSAGE = "সেভ হয়েছে। কিছু বলো না। এখনই end_call টুল কল করো।"


def tool_schemas(flow: Flow) -> ToolsSchema:
    no_args: dict = {}
    tools = [
        FunctionSchema(
            name="save_details",
            description=(
                "কাস্টমারের দেওয়া প্রতিটি তথ্য সাথে সাথে এখানে সেভ করো — একসাথে একাধিক "
                "ফিল্ড পাঠানো যায়। ফলাফলের instruction-ই তোমার পরের কথা।"
            ),
            properties=flow.slot_properties(),
            required=[],
        )
    ]
    for terminal in flow.terminals():
        tools.append(
            FunctionSchema(
                name=terminal.name,
                description=terminal.description_bn,
                properties=terminal.properties,
                required=[],
            )
        )
    tools.append(
        FunctionSchema(
            name="transfer_to_human",
            description="কাস্টমার মানুষের সাথে কথা বলতে চাইলে বা তুমি উত্তর দিতে না পারলে এটি কল করো।",
            properties=no_args,
            required=[],
        )
    )
    tools.append(
        FunctionSchema(
            name="end_call",
            description="বিদায় জানানোর পরে কলটি শেষ করতে এটি কল করো।",
            properties=no_args,
            required=[],
        )
    )
    return ToolsSchema(standard_tools=tools)


def _terminal_note(terminal: Terminal, arguments: dict) -> str:
    """Fill the terminal's Bengali note template from the tool arguments."""
    if not terminal.note_bn:
        return ""
    values = {key: str(arguments.get(key, "") or "").strip() for key in terminal.properties}
    if not any(values.values()):
        return ""
    return terminal.note_bn.format(**values)


class FlowCallTools:
    """Closure over one call's order/merchant/flow, registered on the LLM service."""

    def __init__(self, order_id: str, call_sid: str, support_phone: str, runtime: FlowRuntime):
        self.order_id = order_id
        self.call_sid = call_sid
        self.support_phone = support_phone
        self.runtime = runtime
        self.outcome: str = ""

    def register(self, llm) -> None:
        # cancel_on_interruption=False: a customer talking over the agent must
        # never cancel the DB write that records the call outcome.
        llm.register_function("save_details", self.save_details, cancel_on_interruption=False)
        for terminal in self.runtime.flow.terminals():
            llm.register_function(
                terminal.name, self._terminal_handler(terminal), cancel_on_interruption=False
            )
        llm.register_function(
            "transfer_to_human", self.transfer_to_human, cancel_on_interruption=False
        )
        llm.register_function("end_call", self.end_call, cancel_on_interruption=False)

    # ---- slot filling ----------------------------------------------------

    async def save_details(self, params: FunctionCallParams):
        result = self.runtime.save(dict(params.arguments or {}))
        await params.result_callback(result)

    # ---- terminals -------------------------------------------------------

    def _terminal_handler(self, terminal: Terminal):
        async def handler(params: FunctionCallParams):
            arguments = dict(params.arguments or {})
            await self._set_outcome(
                terminal.status,
                terminal.outcome,
                note=_terminal_note(terminal, arguments),
                extra_data=arguments,
            )
            await params.result_callback({"ok": True, "message": AFTER_TERMINAL_MESSAGE})

        return handler

    async def _set_outcome(
        self,
        status: OrderStatus,
        outcome: str,
        note: str = "",
        extra_data: dict | None = None,
    ) -> None:
        self.outcome = outcome
        async with AsyncSessionLocal() as db:
            order = await db.get(Order, self.order_id)
            if order:
                order.status = status
                if note:
                    order.notes = (order.notes + "\n" if order.notes else "") + note
                # Snapshot everything the flow collected for the merchant UI.
                order.flow_data = self.runtime.flow_data(extra=extra_data)
            log = (
                await db.execute(
                    select(CallLog).where(CallLog.twilio_call_sid == self.call_sid)
                )
            ).scalar_one_or_none()
            if log:
                log.outcome = outcome
                log.final_node = self.runtime.current_node
            await db.commit()
        logger.info(f"Order {self.order_id} outcome: {outcome}")

    # ---- shared tools ----------------------------------------------------

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
        # Wrap-up paths (wrong number / relay) may not have hit a terminal
        # tool; settle the order here so the merchant sees why it needs a look.
        if not self.outcome:
            slots = self.runtime.slots
            if slots.get("knows_customer") is True:
                await self._set_outcome(
                    OrderStatus.needs_review,
                    "relay",
                    note="কল ধরা ব্যক্তি কাস্টমারকে চেনেন; কনফার্ম করতে বলা হয়েছে",
                )
            elif slots.get("knows_customer") is False or slots.get("wrong_person"):
                await self._set_outcome(
                    OrderStatus.needs_review,
                    "wrong_number",
                    note="কলে ভুল নম্বর পাওয়া গেছে",
                )
        line = self.runtime.flow.closing_line_bn(
            self.runtime.merchant,
            self.runtime.order,
            self.outcome,
            self.runtime.slots,
        )
        await params.result_callback({"ok": True})
        await params.llm.push_frame(TTSSpeakFrame(line))
        await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
