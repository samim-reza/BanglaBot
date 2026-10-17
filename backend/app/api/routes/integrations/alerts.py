"""Owner alerts: which events go by email / text, the owner's mobile number, a test alert."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.api.routes.integrations.summary import _summary
from app.core.ratelimit.limiter import rate_limit
from app.core.regions import normalize_phone, region_of
from app.db.session import get_db
from app.models import Merchant
from app.services import alerts

router = APIRouter()

#: "Send test alert" per account: a few tries, then wait (each one may cost a text).
TEST_ALERTS_PER_WINDOW = 3
TEST_ALERT_WINDOW_SECONDS = 600

Event = Literal["booking", "change", "message", "urgent"]


class AlertSettingsIn(BaseModel):
    email_events: list[Event] | None = Field(default=None, max_length=4)
    sms_events: list[Event] | None = Field(default=None, max_length=4)
    sms_to: str | None = Field(default=None, max_length=32)


def _mobile(value: str, merchant: Merchant) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if len(re.sub(r"\D", "", raw)) < 7:
        raise HTTPException(status_code=422, detail="Enter the mobile number with its country code, e.g. +1 617 555 0100.")
    return normalize_phone(raw, region_of(merchant))


@router.patch("/alerts")
async def update_alerts(
    data: AlertSettingsIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    current = alerts.settings_of(merchant)
    values = data.model_dump(exclude_unset=True)
    for key in ("email_events", "sms_events"):
        if values.get(key) is not None:
            current[key] = [event for event in alerts.EVENTS if event in values[key]]
    if values.get("sms_to") is not None:
        current["sms_to"] = _mobile(values["sms_to"], merchant)
    if current["sms_events"] and not current["sms_to"]:
        raise HTTPException(status_code=422, detail="Add the mobile number alerts are texted to.")
    merchant.alert_settings = current
    await db.commit()
    await db.refresh(merchant)
    return await _summary(request, merchant, db)


@router.post("/alerts/test")
async def test_alert(request: Request, merchant: Merchant = Depends(get_current_merchant)):
    await rate_limit(request, "owner-alert-test", max_hits=TEST_ALERTS_PER_WINDOW, per_seconds=TEST_ALERT_WINDOW_SECONDS, key=str(merchant.id))
    if not alerts.email_to(merchant) and not alerts.settings_of(merchant)["sms_to"]:
        raise HTTPException(status_code=422, detail="Add an email or a mobile number first.")
    return {"results": await alerts.send_test(merchant)}
