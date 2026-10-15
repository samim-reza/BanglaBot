"""The call-flow editor service: one settings document across inbound + outbound, locks, preview, saving."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.pipeline.config import FlowConfigError
from app.services import agent_flow_service as svc
from app.verticals import get_vertical
from tests.test_pipeline import Account


class FakeDB:
    def __init__(self) -> None:
        self.added: list = []
        self.commits = 0

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture(autouse=True)
def no_warm(monkeypatch):
    monkeypatch.setattr(svc, "schedule_warm", lambda merchant: None)


def test_shared_steps_validate_once_for_both_directions():
    clinic = get_vertical("clinic")
    cleaned = svc.clean_for_vertical(
        clinic,
        {"steps": {"farewell": {"lines": {"en": {"farewell": "Take care!"}}}, "doctor": {"lines": {"en": {"doctor": "Who would you like to see?"}}},
                   "attend": {"lines": {"en": {"attend": "Can you make it {when}?"}}}}},
        locks=None,
    )
    assert set(cleaned["steps"]) == {"farewell", "doctor", "attend"}
    with pytest.raises(FlowConfigError) as err:
        svc.clean_for_vertical(clinic, {"steps": {"teleport": {}}}, locks=None)
    assert err.value.errors[0]["path"] == "steps.teleport"


def test_locks_apply_only_to_pipelines_that_have_the_step():
    clinic = get_vertical("clinic")
    locks = {"locks": {"steps.payment.options.mode": "online_required", "steps.farewell.enabled": True}}
    inbound, outbound = clinic.blueprints["inbound"], clinic.blueprints["outbound"]
    assert set(svc.locks_for(inbound, locks)["locks"]) == {"steps.payment.options.mode", "steps.farewell.enabled"}
    assert set(svc.locks_for(outbound, locks)["locks"]) == {"steps.farewell.enabled"}
    # A locked payment mode doesn't make an unrelated outbound-only edit fail.
    svc.clean_for_vertical(clinic, {"steps": {"new_time": {"lines": {"en": {"new_time": "Another day?"}}}}}, locks=locks)


def test_lines_only_plans_may_reword_but_not_restructure():
    clinic = get_vertical("clinic")
    svc.clean_for_vertical(clinic, {"steps": {"farewell": {"lines": {"en": {"farewell": "Bye!"}}}}}, locks=None, lines_only=True)
    with pytest.raises(FlowConfigError):
        svc.clean_for_vertical(clinic, {"steps": {"payment": {"enabled": True}}}, locks=None, lines_only=True)


def test_describe_and_preview():
    merchant = Account(agent_flow={"_v": 1, "steps": {"payment": {"enabled": True}}})
    described = svc.describe(merchant)
    assert set(described["directions"]) == {"inbound", "outbound"} and described["hash"]
    assert described["directions"]["inbound"]["effective"]["steps"]["payment"]["enabled"] is True
    preview = svc.preview(merchant)
    book = next(b for b in preview["directions"]["inbound"]["branches"] if b["key"] == "book")
    assert [s["skill"] for s in book["steps"]][:3] == ["intent", "doctor", "schedule"]
    assert any(s["skill"] == "payment" for s in book["steps"])
    assert preview["directions"]["inbound"]["opening"].startswith("Hello, thank you for calling CityCare")


@pytest.mark.asyncio
async def test_save_rejects_a_stale_editor_and_audits_a_good_save():
    merchant = Account()
    db = FakeDB()
    with pytest.raises(HTTPException) as err:
        await svc.save(db, merchant, {}, base_hash="stale", actor={"type": "merchant", "id": "m1"})
    assert err.value.status_code == 409
    current = svc.state_hash(merchant)
    result = await svc.save(db, merchant, {"steps": {"consent": {"enabled": True}}}, base_hash=current, actor={"type": "merchant", "id": "m1"})
    assert merchant.agent_flow["steps"]["consent"] == {"enabled": True} and db.commits == 1
    assert result["hash"] != current and db.added  # the audit event


@pytest.mark.asyncio
async def test_owner_cannot_change_a_locked_setting_but_admin_can_lock_it():
    merchant = Account()
    db = FakeDB()
    await svc.save_locks(db, merchant, {"locks": {"steps.payment.enabled": None}}, actor={"type": "admin", "id": "a1"})
    assert merchant.agent_flow_locks["locks"] == {"steps.payment.enabled": False}  # null froze the current value
    with pytest.raises(FlowConfigError) as err:
        await svc.save(db, merchant, {"steps": {"payment": {"enabled": True}}}, base_hash=None, actor={"type": "merchant", "id": "m1"})
    assert err.value.locked == ["steps.payment.enabled"]
    with pytest.raises(FlowConfigError):
        await svc.save_locks(db, merchant, {"locks": {"steps.teleport.enabled": True}}, actor={"type": "admin", "id": "a1"})
