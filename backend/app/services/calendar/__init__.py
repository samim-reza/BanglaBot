"""Calendar sync, both directions.

**Out — bookings into the business's calendar**

- *Calendar feed* (no setup): ``/api/public/calendar/{token}.ics`` (whole account)
  or ``…?item={catalog_item_id}`` (one doctor) — subscribe from Google Calendar,
  Outlook or Apple Calendar ("add calendar from URL").
- *Google Calendar* (optional, OAuth): every booking / move / cancellation is
  written to the chosen calendar (a doctor's own calendar if mapped) within
  seconds, tagged with the record id so we never mistake it for a busy time.

**In — busy times that block booking slots**

- iCal links: the account's (``calendar_settings.busy_ics_urls``) and each
  doctor's (``catalog item data.calendar_ics``).
- Google: the connected calendar(s), via ``events.list`` (our own events skipped).

Busy times are cached per account (``CALENDAR_BUSY_CACHE_SECONDS``) and served
stale-while-revalidate, so a call never waits on a slow calendar server.

Modules: ``common`` (HTTP seam, settings, time zone), ``ics_feed`` (iCal out), ``busy``
(busy times in + cache), ``google_oauth`` (connect / tokens / revoke), ``google_sync``
(Calendar API: busy reads, event mirroring). ``app.services.calendar_service``
re-exports all of it (the import path callers use).
"""

from app.services.calendar.busy import (
    FIRST_FETCH_WAIT,
    MAX_ICS_BYTES,
    busy_for,
    fetch_ics_busy,
    invalidate_busy,
    sources,
)
from app.services.calendar.common import EVENT_TAG, FETCH_TIMEOUT, LIVE, http, settings_of
from app.services.calendar.ics_feed import event_for, feed, merchant_for_feed_token, new_token
from app.services.calendar.google_oauth import (
    GOOGLE_AUTH_URL,
    GOOGLE_REVOKE_URL,
    GOOGLE_SCOPES,
    GOOGLE_TOKEN_URL,
    access_token,
    auth_url,
    exchange_code,
    google_available,
    merchant_from_state,
    redirect_uri,
    revoke,
)
from app.services.calendar.google_sync import (
    GOOGLE_API,
    delete_event,
    google_busy,
    google_event_body,
    list_calendars,
    sync_record,
)

__all__ = [
    "EVENT_TAG",
    "FETCH_TIMEOUT",
    "FIRST_FETCH_WAIT",
    "GOOGLE_API",
    "GOOGLE_AUTH_URL",
    "GOOGLE_REVOKE_URL",
    "GOOGLE_SCOPES",
    "GOOGLE_TOKEN_URL",
    "LIVE",
    "MAX_ICS_BYTES",
    "access_token",
    "auth_url",
    "busy_for",
    "delete_event",
    "event_for",
    "exchange_code",
    "feed",
    "fetch_ics_busy",
    "google_available",
    "google_busy",
    "google_event_body",
    "http",
    "invalidate_busy",
    "list_calendars",
    "merchant_for_feed_token",
    "merchant_from_state",
    "new_token",
    "redirect_uri",
    "revoke",
    "settings_of",
    "sources",
    "sync_record",
]
