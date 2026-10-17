"""Add-on integrations of an account: SMS confirmations and calendar sync.

One combined ``router`` assembled from ``summary`` (``GET /api/integrations``),
``sms``, ``alerts``, ``calendar`` and ``google``. The prefix is given when each part is included
(FastAPI only allows the summary's empty path under an include-time prefix).
"""

from fastapi import APIRouter

from app.api.routes.integrations import alerts, calendar, google, sms, summary
from app.api.routes.integrations.alerts import AlertSettingsIn
from app.api.routes.integrations.calendar import CalendarCheckIn, CalendarIn, ItemCalendarIn
from app.api.routes.integrations.google import GoogleIn
from app.api.routes.integrations.sms import SendSmsIn, SmsSettingsIn, SmsTestIn

router = APIRouter()
for _module in (summary, sms, alerts, calendar, google):
    router.include_router(_module.router, prefix="/api/integrations", tags=["integrations"])

__all__ = ["AlertSettingsIn", "CalendarCheckIn", "CalendarIn", "GoogleIn", "ItemCalendarIn", "SendSmsIn", "SmsSettingsIn", "SmsTestIn", "router"]
