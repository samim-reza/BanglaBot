"""Emergencies on a phone call: offer to connect, put through on a yes, carry on otherwise."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.runtime import FlowRuntime
from app.services.calls import control
from app.verticals import flow_for
from app.voice import emergency_dial
from app.voice.agent import CallAgent
from app.voice.bridge.hangup import HangupMixin
from app.voice.tools import CallTools, NullCallStore
from app.voice.tools.emergency import wants_connection
from app.voice.twiml import dial_twiml
from tests.test_verticals import DOCTORS, NOW, Account


@dataclass
class FlowAccount(Account):
    agent_flow: dict = field(default_factory=dict)


def _ctx(vertical: str = "clinic", **account: Any) -> CallContext:
    return CallContext(merchant=FlowAccount(vertical, **account), catalog=list(DOCTORS), direction=DIRECTION_INBOUND, now=NOW, caller_number="+16175550100")


def _tools(ctx: CallContext, *, phone_call: bool = True) -> tuple[CallTools, NullCallStore]:
    store = NullCallStore()
    runtime = FlowRuntime(flow_for(ctx.merchant, ctx.direction), ctx, language="en")
    return CallTools(runtime, store, phone_call=phone_call), store


def _options(**options: Any) -> dict:
    return {"_v": 1, "steps": {"emergency": {"options": options}}}


@pytest.mark.asyncio
async def test_phone_emergency_offers_to_connect_instead_of_hanging_up():
    tools, store = _tools(_ctx())
    result = await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    assert not result.hang_up and not result.transfer_to and not result.outcome
    assert "call nine one one" in result.say and result.say.endswith("Would you like me to connect you to nine one one now?")
    assert not store.outcomes  # nothing decided yet: the caller answers the offer


@pytest.mark.asyncio
async def test_yes_puts_the_caller_through_and_keeps_it_as_an_emergency():
    tools, store = _tools(_ctx())
    await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    result = await tools.execute("report_emergency", {}, caller_text="yes please, hurry")
    assert result.outcome == "emergency" and result.transfer_to == emergency_dial.mark("911") and not result.hang_up
    assert result.say == "Connecting you now. Tell them your exact address right away."
    assert store.outcomes[-1]["status"] == "needs_review" and "chest pain — put through to 911" in store.outcomes[-1]["note"]


@pytest.mark.asyncio
async def test_connect_tool_works_when_the_model_hears_the_yes():
    tools, _ = _tools(_ctx())
    await tools.execute("report_emergency", {"what": "stroke"}, caller_text="I think my mom is having a stroke")
    result = await tools.execute("connect_emergency", {}, caller_text="can you connect me?")
    assert result.transfer_to == emergency_dial.mark("911") and result.outcome == "emergency"


@pytest.mark.asyncio
async def test_a_caller_who_wants_something_else_keeps_talking():
    tools, store = _tools(_ctx())
    await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    again = await tools.execute("report_emergency", {}, caller_text="no, he's fine now, I just want to book a check-up")
    assert again.payload["reason"] == "already_offered" and not again.say and not again.hang_up
    result = await tools.execute("save_details", {"intent": "book", "doctor": "D1"}, caller_text="a check-up with Dr Mitchell")
    assert result.payload.get("ok") is not False and not result.hang_up and not store.outcomes


@pytest.mark.asyncio
async def test_ending_after_a_declined_offer_still_says_where_to_get_help():
    tools, store = _tools(_ctx())
    await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    result = await tools.execute("end_call", {"reason": "caller will call 911 themselves"}, caller_text="no, I'll call them myself, bye")
    assert result.hang_up and result.outcome == "emergency"
    assert result.say == "Okay. Please stay safe, and call nine one one if you need help. Goodbye."
    assert "didn't want to be put through" in store.outcomes[-1]["note"]


@pytest.mark.asyncio
async def test_hanging_up_or_silence_after_the_offer_is_kept_as_an_emergency():
    tools, store = _tools(_ctx())
    await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    await tools.finish_inbound()
    assert store.outcomes[-1]["outcome"] == "emergency" and "hung up after the offer" in store.outcomes[-1]["note"]

    tools, store = _tools(_ctx())
    await tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    line = await tools.settle("auto_dropped")
    assert "call nine one one" in line and store.outcomes[-1]["outcome"] == "emergency"


@pytest.mark.asyncio
async def test_chats_and_switched_off_accounts_keep_the_plain_ending():
    chat, _ = _tools(_ctx(), phone_call=False)
    result = await chat.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    assert result.hang_up and result.outcome == "emergency" and "connect" not in result.say
    result = await chat.execute("connect_emergency", {}, caller_text="connect me")
    assert not result.transfer_to

    off, _ = _tools(_ctx(agent_flow=_options(connect=False)))
    result = await off.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    assert result.hang_up and result.outcome == "emergency" and not result.transfer_to


@pytest.mark.asyncio
async def test_on_call_line_is_offered_by_name_and_dialled():
    tools, _ = _tools(_ctx("home_service", agent_flow=_options(connect_to="+1 415 555 0177")))
    result = await tools.execute("report_emergency", {"what": "gas smell"}, caller_text="I smell gas in the kitchen")
    assert result.say.endswith("Would you like me to connect you to our emergency line now?")
    result = await tools.execute("report_emergency", {}, caller_text="yes")
    assert result.transfer_to == emergency_dial.mark("+1 415 555 0177")


@pytest.mark.asyncio
async def test_vet_offers_only_the_emergency_vet_never_911():
    plain, _ = _tools(_ctx("vet"))
    result = await plain.execute("report_emergency", {"what": "ate chocolate"}, caller_text="my dog ate a whole bar of chocolate")
    assert result.hang_up and "connect" not in result.say

    tools, _ = _tools(_ctx("vet", vertical_config={"emergency_vet": "Harbor Animal ER"}, agent_flow=_options(connect_to="+14155550188")))
    result = await tools.execute("report_emergency", {"what": "ate chocolate"}, caller_text="my dog ate a whole bar of chocolate")
    assert result.say.endswith("Would you like me to connect you to Harbor Animal ER now?")
    result = await tools.execute("report_emergency", {}, caller_text="yes please")
    assert result.transfer_to == emergency_dial.mark("+14155550188")


@pytest.mark.parametrize(
    ("text", "yes"),
    [
        ("yes please", True), ("Yeah, connect me", True), ("put me through", True), ("call 911", True), ("hurry", True),
        ("yes, he's not breathing, connect me", True), ("okay", True),
        ("no", False), ("no thanks", False), ("don't connect me", False), ("I'll call them myself", False),
        ("What's the address of the hospital?", False), ("I just want to book an appointment", False),
    ],
)
def test_what_counts_as_a_yes_to_the_offer(text: str, yes: bool):
    assert wants_connection(text) is yes


class _Speaker:
    def __init__(self) -> None:
        self.closing = False
        self.spoken: list[dict[str, Any]] = []

    def speak(self, text: str, **kwargs: Any) -> None:
        self.spoken.append({"text": text, **kwargs})


@pytest.mark.asyncio
async def test_a_plain_yes_connects_without_the_model():
    ctx = _ctx()
    speaker = _Speaker()
    agent = CallAgent(flow=flow_for(ctx.merchant, ctx.direction), ctx=ctx, store=NullCallStore(), speaker=speaker, language="en", settings=SimpleNamespace(), phone_call=True)
    await agent.tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    assert await agent._fast_path("yes please") is True
    assert speaker.spoken[-1]["transfer_to"] == emergency_dial.mark("911") and speaker.closing

    agent = CallAgent(flow=flow_for(ctx.merchant, ctx.direction), ctx=ctx, store=NullCallStore(), speaker=_Speaker(), language="en", settings=SimpleNamespace(), phone_call=True)
    await agent.tools.execute("report_emergency", {"what": "chest pain"}, caller_text="my father has chest pain")
    assert await agent._fast_path("no, actually I want to book") is False  # the model takes it from here
    assert not agent.tools.emergency_offer_pending()


def test_emergency_dial_keeps_the_short_code_and_says_where_to_dial_after():
    texml = dial_twiml("911", caller_id="+18723428160", timeout_seconds=30, after_say="If you still need help, hang up and dial nine one one now.")
    assert "<Dial timeout=\"30\" callerId=\"+18723428160\">911</Dial><Say language=\"en-US\">If you still need help" in texml
    assert texml.endswith("<Hangup/></Response>")


@pytest.mark.asyncio
async def test_redirect_to_emergency_never_turns_911_into_a_phone_number(monkeypatch: pytest.MonkeyPatch):
    sent: list[str] = []

    async def update_call(call_sid: str, *, texml: str) -> None:
        sent.append(texml)

    monkeypatch.setattr(control.telnyx, "configured", lambda: True)
    monkeypatch.setattr(control.telnyx, "update_call", update_call)
    assert await control.redirect_call_to_emergency("v3:abc", "911", "US", caller_id="+18723428160", after="dial nine one one")
    assert ">911</Dial>" in sent[-1]
    assert await control.redirect_call_to_emergency("v3:abc", "(415) 555-0177", "US", caller_id="+18723428160")
    assert ">+14155550177</Dial>" in sent[-1]


class _Bridge(HangupMixin):
    """Just enough of a phone bridge for the transfer step."""

    def __init__(self, dial_ok: bool) -> None:
        self.ctx = _ctx()
        self.active_language = "en"
        self.messages: list[dict[str, Any]] = []
        self.spoken: list[tuple[str, dict[str, Any]]] = []
        self.call_log_id, self.call_sid, self.web = "c1", "v3:abc", False
        self.merchant = SimpleNamespace(region="US")
        self.dialled: list[str] = []
        self._dial_ok = dial_ok
        self.closed_quietly = False

    def speak(self, text: str, **kwargs: Any) -> None:
        self.spoken.append((text, kwargs))

    async def _dial_emergency(self, number: str) -> bool:
        self.dialled.append(number)
        return self._dial_ok

    async def _safe_close(self, **kwargs: Any) -> None:
        self.closed_quietly = kwargs.get("end_phone_call") is False


@pytest.mark.asyncio
async def test_bridge_dials_emergency_and_tells_the_caller_when_it_cant(monkeypatch: pytest.MonkeyPatch):
    import asyncio

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    bridge = _Bridge(dial_ok=True)
    await bridge._transfer_call(emergency_dial.mark("911"))
    assert bridge.dialled == ["911"] and bridge.closed_quietly and not bridge.spoken

    bridge = _Bridge(dial_ok=False)
    await bridge._transfer_call(emergency_dial.mark("911"))
    text, kwargs = bridge.spoken[-1]
    assert text == "I couldn't connect the call. Please hang up and dial nine one one right now." and kwargs["close_after"]
