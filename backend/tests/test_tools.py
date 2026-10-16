"""CallTools against the in-memory store: hearing gates, re-ask ladder, identity vetting."""

import pytest

from app.flows.base import OUTCOME_CONFIRMED, OUTCOME_UNCLEAR, STAGE_DECISION, STAGE_RELAY
from app.verticals.ecommerce import DEFAULT_FLOW
from app.flows.runtime import FlowRuntime
from app.voice.languages import phrase
from app.voice.tools import CallTools, NullCallStore


def _ctx(order, merchant):
    from app.flows.context import CallContext

    return CallContext(merchant=merchant, record=order)


def _tools(order, merchant, language="en", support_phone=""):
    rt = FlowRuntime(DEFAULT_FLOW, _ctx(order, merchant), language=language)
    store = NullCallStore()
    return CallTools(rt, store, support_phone=support_phone), rt, store


def test_schemas_list_every_tool(order, merchant):
    tools, _, _ = _tools(order, merchant)
    names = [t["function"]["name"] for t in tools.schemas()]
    assert names == ["save_details", "confirm_order", "cancel_order", "transfer_to_human", "end_call"]
    assert "address_correct" in tools.schemas()[0]["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_confirm_requires_identity_then_a_clear_yes(order, merchant):
    tools, rt, store = _tools(order, merchant)
    # Before identity: refused with the identity instruction.
    result = await tools.execute("confirm_order", "{}", caller_text="yes")
    assert result.payload["reason"] == "identity_not_confirmed" and not result.outcome
    await tools.execute("save_details", '{"identity_confirmed": true}', caller_text="yes, speaking")
    assert rt.stage == STAGE_DECISION
    result = await tools.execute("confirm_order", "{}", caller_text="yes, that's fine")
    assert result.outcome == OUTCOME_CONFIRMED and result.hang_up and result.stop
    assert result.say == phrase("closing_confirmed", "en")
    assert store.outcomes[-1]["status"] == "confirmed" and store.outcomes[-1]["final_node"] == "wrap_up"
    # A second terminal after the outcome is a no-op.
    again = await tools.execute("cancel_order", "{}", caller_text="no")
    assert again.stop and not again.say


@pytest.mark.asyncio
async def test_unclear_answers_are_reasked_twice_then_needs_review(order, merchant):
    tools, rt, store = _tools(order, merchant)
    await tools.execute("save_details", '{"identity_confirmed": true}', caller_text="yes")
    first = await tools.execute("confirm_order", "{}", caller_text="what did you say")
    assert first.say == phrase("decision_reask_1", "en") and first.stop and not first.hang_up
    second = await tools.execute("confirm_order", "{}", caller_text="sorry, what?")
    assert second.say == phrase("decision_reask_2", "en")
    third = await tools.execute("cancel_order", "{}", caller_text="I didn't understand")
    assert third.outcome == OUTCOME_UNCLEAR and third.hang_up
    assert third.say == phrase("closing_unclear", "en")
    assert store.outcomes[-1]["status"] == "needs_review" and rt.outcome == OUTCOME_UNCLEAR


@pytest.mark.asyncio
async def test_cancel_with_reason_writes_note(order, merchant):
    tools, _, store = _tools(order, merchant, language="en")
    await tools.execute("save_details", '{"identity_confirmed": true}', caller_text="yes speaking")
    result = await tools.execute("cancel_order", '{"reason": "found it cheaper"}', caller_text="no, cancel it")
    assert result.outcome == "cancelled" and store.outcomes[-1]["note"] == "Customer cancelled: found it cheaper"
    assert result.say == phrase("closing_cancelled", "en")


@pytest.mark.asyncio
async def test_later_settles_as_callback(order, merchant):
    tools, _, store = _tools(order, merchant)
    await tools.execute("save_details", '{"identity_confirmed": true}', caller_text="yes")
    result = await tools.execute("cancel_order", "{}", caller_text="not now, call me later")
    assert result.outcome == OUTCOME_UNCLEAR and result.say == phrase("closing_callback", "en")
    assert "later" in store.outcomes[-1]["note"]


@pytest.mark.asyncio
async def test_identity_denial_must_be_backed_by_caller_words(order, merchant):
    tools, rt, _ = _tools(order, merchant)
    result = await tools.execute("save_details", '{"identity_confirmed": false}', caller_text="yes hello")
    assert result.payload["rejected"] == ["identity_confirmed"] and "identity_confirmed" not in rt.slots
    assert phrase("identity_reask", "en", customer_name=order.customer_name) in result.payload["instruction"]
    result = await tools.execute("save_details", '{"identity_confirmed": false, "knows_customer": true}', caller_text="I'm his brother")
    assert "rejected" not in result.payload and rt.stage == STAGE_RELAY
    # And a confirmation is never accepted on filler or a denial.
    tools2, rt2, _ = _tools(order, merchant)
    result = await tools2.execute("save_details", '{"identity_confirmed": true}', caller_text="hmm")
    assert result.payload["rejected"] == ["identity_confirmed"] and rt2.stage == "identity"


@pytest.mark.asyncio
async def test_end_call_settles_relay_and_wrong_number(order, merchant):
    tools, _, store = _tools(order, merchant)
    # Reaching the wrap-up through save_details closes the call right there.
    saved = await tools.execute("save_details", '{"identity_confirmed": false, "knows_customer": true}', caller_text="no, I'm her sister")
    assert saved.outcome == "relay" and saved.hang_up and store.outcomes[-1]["status"] == "needs_review"
    assert saved.say == phrase("relay_line", "en", customer_name=order.customer_name, business_name=merchant.business_name)
    # A later end_call from the model is a no-op hang-up that still reports the outcome.
    result = await tools.execute("end_call", '{"reason": "relay"}', caller_text="okay")
    assert result.outcome == "relay" and result.hang_up and result.say == ""
    tools2, _, store2 = _tools(order, merchant, language="en")
    saved = await tools2.execute("save_details", '{"wrong_person": true}', caller_text="wrong number")
    assert saved.outcome == "wrong_number" and saved.say == phrase("wrong_number_line", "en") and saved.hang_up
    result = await tools2.execute("end_call", "{}", caller_text="wrong number")
    assert result.outcome == "wrong_number" and result.hang_up


@pytest.mark.asyncio
async def test_transfer_with_and_without_support_phone(order, merchant):
    tools, _, _ = _tools(order, merchant, support_phone="+14155550199")
    result = await tools.execute("transfer_to_human", '{"reason": "discount"}', caller_text="I want to talk to a person")
    assert result.outcome == "transfer" and result.transfer_to == "+14155550199" and not result.hang_up
    assert result.say == phrase("closing_transfer", "en")
    tools2, _, store2 = _tools(order, merchant)
    result = await tools2.execute("transfer_to_human", "{}", caller_text="give me a real person")
    assert result.hang_up and result.say == phrase("closing_transfer_callback", "en")
    assert store2.outcomes[-1]["status"] == "needs_review"


@pytest.mark.asyncio
async def test_settle_auto_dropped(order, merchant):
    tools, _, store = _tools(order, merchant)
    line = await tools.settle("auto_dropped")
    assert line == phrase("closing_dropped", "en")
    assert store.outcomes[-1]["status"] == "no_answer" and tools.outcome == "auto_dropped"


@pytest.mark.asyncio
async def test_bare_no_is_not_a_wrong_number(order, merchant):
    """The model may jump to wrong_person on a bare "no"; the backend keeps only identity_confirmed=False."""
    from app.flows.base import STAGE_KNOWS_PERSON
    from app.flows.runtime import FlowRuntime
    from app.verticals.ecommerce import DEFAULT_FLOW
    from app.voice.tools import CallTools, NullCallStore

    runtime = FlowRuntime(DEFAULT_FLOW, _ctx(order, merchant), language="en")
    tools = CallTools(runtime, NullCallStore())
    result = await tools.execute("save_details", {"identity_confirmed": False, "wrong_person": True}, caller_text="no.")
    assert runtime.stage == STAGE_KNOWS_PERSON
    assert runtime.slots.get("wrong_person") is None and runtime.slots.get("identity_confirmed") is False
    assert "wrong_person" in result.payload.get("rejected", [])
    assert not result.hang_up


@pytest.mark.asyncio
async def test_save_details_reaching_wrap_up_closes_the_call(order, merchant):
    from app.flows.runtime import FlowRuntime
    from app.verticals.ecommerce import DEFAULT_FLOW
    from app.voice.tools import CallTools, NullCallStore

    runtime = FlowRuntime(DEFAULT_FLOW, _ctx(order, merchant), language="en")
    tools = CallTools(runtime, NullCallStore())
    await tools.execute("save_details", {"identity_confirmed": False}, caller_text="no")
    result = await tools.execute("save_details", {"knows_customer": False}, caller_text="no, I don't know them")
    assert result.hang_up and result.say and tools.outcome == "wrong_number"
