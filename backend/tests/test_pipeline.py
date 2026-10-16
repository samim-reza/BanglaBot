"""The skill pipeline: skip-when-known, owner settings, admin locks, the compile cache,
and the optional clinic skills (patient type, intake fields, visit mode, payment, consent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime
from app.flows.timefmt import business_tz
from app.pipeline.compiled import PIPELINES, PipelineCache
from app.pipeline.config import FlowConfigError, config_hash, effective
from app.pipeline.validate import clean_agent_flow, clean_locks
from app.skills.base import render
from app.verticals import flow_for
from app.verticals.clinic.blueprint import INBOUND
from app.voice.tools import CallTools, NullCallStore

NY = business_tz("America/New_York")
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=NY)  # Friday 8 pm

DOCTORS = [
    CatalogEntry("doc-mitchell", "D1", "doctor", "Dr. Sarah Mitchell", {"specialty": "Family Medicine", "days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "slot_minutes": 20, "fee": 150}),
    CatalogEntry("doc-carter", "D2", "doctor", "Dr. James Carter", {"specialty": "Pediatrics", "days": ["mon", "wed", "fri"], "start_time": "10:00", "end_time": "16:00", "slot_minutes": 20, "fee": 140}),
]


@dataclass
class Account:
    vertical: str = "clinic"
    business_name: str = "CityCare"
    language: str = "en"
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"
    custom_greeting: str = ""
    support_phone: str = ""
    knowledge: str = ""
    vertical_config: dict = field(default_factory=dict)
    voice_persona: str = "female"
    sms_settings: dict = field(default_factory=dict)
    agent_flow: dict = field(default_factory=dict)
    agent_flow_locks: dict = field(default_factory=dict)
    plan: str = "pro"
    id: str = "m1"


def _call(agent_flow: dict | None = None, *, texts: bool = False, **ctx_kwargs: Any) -> tuple[CallTools, FlowRuntime, NullCallStore]:
    # texts=True: the account sends texts (a payment link can go out).
    merchant = Account(agent_flow=agent_flow or {}, sms_settings={"enabled": True} if texts else {})
    ctx = CallContext(merchant=merchant, catalog=list(DOCTORS), direction=DIRECTION_INBOUND, now=NOW, caller_number="+16175550100", **ctx_kwargs)
    runtime = FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en")
    store = NullCallStore()
    return CallTools(runtime, store), runtime, store


def steps(**skills: dict) -> dict:
    return {"_v": 1, "steps": skills}


# ---- templating -------------------------------------------------------------------------------
def test_render_never_formats_objects():
    assert render("Hi {name}!", {"name": "Ana"}) == "Hi Ana!"
    assert render("{x.__class__} {missing}", {}) == "{x.__class__}"


# ---- skip when already known --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_volunteered_details_skip_their_questions():
    tools, runtime, _ = _call(steps(patient_type={"enabled": True}))
    result = await tools.execute(
        "save_details",
        {"intent": "book", "doctor": "D2", "date": "2026-10-07", "patient_type": "new", "patient_name": "Leo"},
        caller_text="I'm new, Leo, the children's doctor on Wednesday",
    )
    # doctor, day, patient type, name were all given; caller ID covers the phone → straight to the read-back.
    assert runtime.stage == "confirm" and "Dr. James Carter" in result.say


@pytest.mark.asyncio
async def test_returning_caller_is_recognised_without_asking():
    tools, runtime, _ = _call(steps(patient_type={"enabled": True}), caller_history=2)
    await tools.execute("save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05"}, caller_text="Dr Mitchell Monday")
    assert runtime.slots["patient_type"] == "existing" and runtime.stage == "patient_name"


# ---- optional skills ----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_online_required_payment_is_read_back_and_holds_the_booking(monkeypatch):
    monkeypatch.setattr("app.services.sms.policy.platform_ready", lambda: True)
    tools, runtime, store = _call(steps(payment={"enabled": True, "options": {"mode": "online_required", "hold_minutes": 20}}), texts=True)
    result = await tools.execute(
        "save_details", {"intent": "book", "doctor": "D2", "date": "2026-10-07", "patient_name": "Leo"}, caller_text="Dr Carter Wednesday, Leo"
    )
    assert "payment link for 140 dollars" in result.say and "20 minutes" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    action = store.commits[0]["action"]
    assert result.outcome == "booked" and action.status == "pending"
    assert action.fields["details"]["payment"]["method"] == "online"
    assert "link in your texts" in result.say


@pytest.mark.asyncio
async def test_online_required_without_texts_is_paid_at_the_visit_not_promised_by_text():
    # No way to send the link (texts off): never promise one, never hold the booking for it.
    tools, runtime, store = _call(steps(payment={"enabled": True, "options": {"mode": "online_required"}}))
    result = await tools.execute(
        "save_details", {"intent": "book", "doctor": "D2", "date": "2026-10-07", "patient_name": "Leo"}, caller_text="Dr Carter Wednesday, Leo"
    )
    assert runtime.stage == "confirm" and "payment link" not in result.say
    await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    action = store.commits[0]["action"]
    assert str(getattr(action.status, "value", action.status)) != "pending"
    assert action.fields["details"]["payment"]["method"] == "at_venue" and action.fields["details"]["payment"]["note"]


@pytest.mark.asyncio
async def test_caller_choice_payment_asks_then_records_the_choice(monkeypatch):
    monkeypatch.setattr("app.services.sms.policy.platform_ready", lambda: True)
    tools, runtime, store = _call(steps(payment={"enabled": True, "options": {"mode": "caller_choice"}}), texts=True)
    result = await tools.execute(
        "save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05", "patient_name": "Jo"}, caller_text="Dr Mitchell Monday, Jo"
    )
    assert runtime.stage == "payment_method" and "pay 150 dollars online" in result.say
    fields = runtime.flow.fast_fields(runtime.stage, "when I arrive", set(), runtime.slots, runtime.ctx)
    assert fields == {"payment_method": "at_venue"}
    result = await tools.execute("save_details", fields, caller_text="when I arrive")
    assert runtime.stage == "confirm" and "paid when you arrive" in result.say


@pytest.mark.asyncio
async def test_separate_consent_needs_the_callers_own_yes():
    tools, runtime, store = _call(steps(consent={"enabled": True, "options": {"mode": "separate"}}))
    result = await tools.execute(
        "save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05", "patient_name": "Jo"}, caller_text="Dr Mitchell Monday, Jo"
    )
    assert runtime.stage == "consent" and "24 hours" in result.say
    result = await tools.execute("save_details", {"consent": True}, caller_text="hmm maybe")
    assert "consent" in result.payload.get("rejected", [])
    await tools.execute("save_details", {"consent": True}, caller_text="yes I agree")
    assert runtime.stage == "confirm"
    await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert "text_sha256" in store.commits[0]["action"].fields["details"]["consent"]


@pytest.mark.asyncio
async def test_visit_mode_fixed_by_owner_is_never_asked():
    tools, runtime, store = _call(steps(visit_mode={"enabled": True, "options": {"mode": "online"}}))
    result = await tools.execute(
        "save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05", "patient_name": "Jo"}, caller_text="Dr Mitchell Monday, Jo"
    )
    assert runtime.stage == "confirm" and "online video consultation" in result.say


@pytest.mark.asyncio
async def test_custom_and_optional_fields_are_asked_once():
    flow = steps(intake={"options": {
        "fields": [{"key": "patient_name", "on": True, "required": True}, {"key": "age", "on": True, "required": False}],
        "custom": [{"key": "referral", "label": "Referral source", "question": "How did you hear about us?", "on": True}],
    }})
    tools, runtime, _ = _call(flow)
    result = await tools.execute("save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05", "patient_name": "Jo"}, caller_text="Monday, Jo")
    assert runtime.stage == "age" and result.say.endswith("How old is the patient?")
    result = await tools.execute("save_details", {"reply": "Sure."}, caller_text="I'd rather not say")
    assert runtime.stage == "f_referral" and "How did you hear about us?" in result.say
    await tools.execute("save_details", {"f_referral": "a friend"}, caller_text="a friend told me")
    assert runtime.stage == "confirm" and runtime.slots["f_referral"] == "a friend"


@pytest.mark.asyncio
async def test_switched_off_branch_is_refused_politely():
    tools, runtime, _ = _call({"_v": 1, "branches": {"cancel": {"enabled": False}}})
    result = await tools.execute("save_details", {"intent": "cancel"}, caller_text="cancel my appointment")
    assert "can't do that over the phone" in result.say and "intent" not in runtime.slots


@pytest.mark.asyncio
async def test_owner_edited_lines_are_spoken():
    flow = steps(intake={"options": {"fields": [{"key": "patient_name", "on": True, "required": True, "question": "Who is the appointment for?"}]}},
                 farewell={"lines": {"en": {"farewell": "Take care!"}}})
    tools, runtime, _ = _call(flow)
    result = await tools.execute("save_details", {"intent": "book", "doctor": "D1", "date": "2026-10-05"}, caller_text="Monday")
    assert result.say.endswith("Who is the appointment for?")
    await tools.execute("save_details", {"patient_name": "Jo"}, caller_text="Jo")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert result.say.endswith("Is there anything else I can help you with?")
    # The owner's farewell is the goodbye once the caller is done.
    result = await tools.execute("end_call", {}, caller_text="no, that's all")
    assert result.say.endswith("Take care!") and result.hang_up


# ---- settings validation, locks, cache ------------------------------------------------------------
def test_unknown_placeholders_and_steps_are_rejected():
    with pytest.raises(FlowConfigError) as err:
        clean_agent_flow(INBOUND, {"steps": {"farewell": {"lines": {"en": {"farewell": "Bye {x.__class__}"}}}, "nope": {}}})
    paths = {e["path"] for e in err.value.errors}
    assert "steps.farewell.lines.en.farewell" in paths and "steps.nope" in paths


def test_required_steps_cannot_be_switched_off_and_order_respects_constraints():
    with pytest.raises(FlowConfigError):
        clean_agent_flow(INBOUND, {"steps": {"doctor": {"enabled": False}}})
    with pytest.raises(FlowConfigError):  # schedule needs the doctor first
        clean_agent_flow(INBOUND, {"order": {"book": ["schedule", "doctor", "patient_type", "intake", "phone", "visit_mode", "payment", "consent"]}})
    ok = clean_agent_flow(INBOUND, {"order": {"book": ["doctor", "intake", "phone", "schedule", "patient_type", "visit_mode", "payment", "consent"]}})
    assert ok["order"]["book"][1] == "intake"


def test_emergency_line_must_keep_the_number():
    with pytest.raises(FlowConfigError):
        clean_agent_flow(INBOUND, {"steps": {"emergency": {"lines": {"en": {"emergency": "Please hang up and call for help."}}}}})


def test_admin_lock_blocks_owner_change_and_wins_in_effect():
    locks = clean_locks(INBOUND, {"locks": {"steps.payment.enabled": True, "steps.payment.options.mode": "online_required"}}, owner=None)
    view = effective(INBOUND, {}, locks)
    assert view["steps"]["payment"]["enabled"] is True and view["steps"]["payment"]["options"]["mode"] == "online_required"
    with pytest.raises(FlowConfigError) as err:
        clean_agent_flow(INBOUND, {"steps": {"payment": {"options": {"mode": "at_venue"}}}}, locks=locks)
    assert "steps.payment.options.mode" in err.value.locked


def test_same_settings_share_one_compiled_flow():
    cache = PipelineCache(size=2)
    owner = clean_agent_flow(INBOUND, {"steps": {"payment": {"enabled": True}}})
    a = cache.get(INBOUND, owner, None)
    b = cache.get(INBOUND, dict(owner), None)
    assert a is b and cache.hits == 1
    assert config_hash(INBOUND, owner, None) != config_hash(INBOUND, None, None)
    default = PIPELINES.get(INBOUND, None, None)
    assert flow_for(Account(), DIRECTION_INBOUND) is default.flow


def test_schema_includes_custom_fields_and_skill_slots_only_when_enabled():
    flow = flow_for(Account(), DIRECTION_INBOUND)
    assert "payment_method" not in flow.slot_properties()
    owner = clean_agent_flow(INBOUND, {"steps": {"payment": {"enabled": True, "options": {"mode": "caller_choice"}},
                                                   "intake": {"options": {"custom": [{"key": "referral", "on": True}]}}}})
    flow = flow_for(Account(agent_flow=owner), DIRECTION_INBOUND)
    props = flow.slot_properties()
    assert "payment_method" in props and "f_referral" in props
