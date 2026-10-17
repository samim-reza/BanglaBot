"""Owner alert wording, pure (no I/O): what happened, who it was, what was booked, the AI
summary and a link to the record in the portal — as an email and as a short text."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from app.services.alerts.settings import EVENT_BOOKING, EVENT_CHANGE, EVENT_MESSAGE, EVENT_URGENT

#: An owner text stays within two GSM-7 segments; the summary is left out when it won't fit.
SMS_MAX_CHARS = 306

CHANNELS = {
    "inbound": "Phone call", "outbound": "Outbound call", "widget": "Website chat", "whatsapp": "WhatsApp",
    "messenger": "Messenger", "instagram": "Instagram", "web": "Test call", "chat": "Test chat",
}
ANONYMOUS = {"widget": "Website visitor", "whatsapp": "WhatsApp user", "messenger": "Messenger user", "instagram": "Instagram user"}
NOUNS = {"order": "order", "appointment": "appointment"}


@dataclass(frozen=True)
class Alert:
    event: str
    title: str
    business: str
    who: str = ""
    phone: str = ""
    what: str = ""
    when: str = ""
    total: str = ""
    ref: str = ""
    channel: str = ""
    summary: str = ""
    link: str = ""
    settings_link: str = ""

    @property
    def urgent(self) -> bool:
        return self.event == EVENT_URGENT

    @property
    def caller(self) -> str:
        """Name and number, whichever are known."""
        return " ".join(part for part in (self.who, self.phone) if part) or "Unknown caller"

    @property
    def details(self) -> list[str]:
        return [part for part in (self.what, self.when, self.total, f"Ref {self.ref}" if self.ref else "") if part]


def title_for(event: str, outcome: str, record_kind: str = "") -> str:
    noun = NOUNS.get(record_kind, "booking")
    if event == EVENT_BOOKING:
        # A customer confirming an existing order on a call isn't a new one.
        return f"{noun.capitalize()} confirmed" if outcome == "confirmed" else f"New {noun}"
    if event == EVENT_CHANGE:
        if outcome == "rescheduled":
            return f"{noun.capitalize()} moved"
        if outcome == "not_interested":
            return "Lead not interested"
        return f"{noun.capitalize()} cancelled"
    if event == EVENT_MESSAGE:
        if outcome == "relay":
            return "Message taken"
        return "New message" if record_kind == "message" else "New lead"
    if event == EVENT_URGENT:
        return {"emergency": "Emergency", "transfer": "Wants a person"}.get(outcome, "Needs review")
    return "Update"


#: A taken message can be long: the alert shows its start (the record has the rest).
WHAT_MAX_CHARS = 80


def _short(text: str) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= WHAT_MAX_CHARS else value[: WHAT_MAX_CHARS - 3].rsplit(" ", 1)[0] + "..."


def portal_url(path: str) -> str:
    from app.services.checkout_port import frontend_base

    return f"{frontend_base()}{path}"


def build(
    merchant: Any, *, event: str, outcome: str, record: Any = None, log: Any = None, item_name: str = "", summary: str = "",
) -> Alert:
    from app.services.sms.composer import _money, _when

    record_kind = str(getattr(record, "kind", "") or "")
    direction = str(getattr(log, "direction", "") or "")
    name = str(getattr(record, "customer_name", "") or "").strip()
    who = name if name and name.lower() != "caller" else ""
    phone = str(getattr(record, "customer_phone", "") or "") or str(getattr(log, "caller_number", "") or "")
    if phone:
        from app.core.regions import normalize_phone, region_of

        phone = normalize_phone(phone, region_of(merchant)) or phone
    if not who and not phone:
        who = ANONYMOUS.get(direction, "")
    total = ""
    if record is not None:
        total = _money(getattr(record, "total_amount", 0), str(getattr(record, "currency", "") or getattr(merchant, "currency", "") or "USD"))
    record_id = str(getattr(record, "id", "") or "")
    return Alert(
        event=event,
        title=title_for(event, outcome, record_kind),
        business=str(getattr(merchant, "business_name", "") or ""),
        who=who,
        phone=phone,
        what=_short(str(getattr(record, "items_summary", "") or "") or item_name),
        when=_when(record, merchant, "en") if record is not None else "",
        total=total,
        ref=str(getattr(record, "order_ref", "") or ""),
        channel=CHANNELS.get(direction, ""),
        summary=" ".join(str(summary or "").split()),
        link=portal_url(f"/orders/{record_id}" if record_id else "/calls"),
        settings_link=portal_url("/settings?tab=notifications"),
    )


def email(alert: Alert) -> tuple[str, str]:
    """``(subject, plain-text body)``."""
    subject = f"{alert.title}: {alert.who or alert.phone or 'Unknown caller'}" + (f", {alert.when}" if alert.when else "")
    if alert.urgent:
        subject = f"Urgent - {subject}"
    lines = [alert.title, "", alert.caller]
    if alert.details:
        lines.append(" · ".join(alert.details))
    if alert.channel:
        lines.append(alert.channel)
    if alert.summary:
        lines += ["", alert.summary]
    lines += ["", f"Open: {alert.link}", "", "--", f"Callisa alert for {alert.business}. Change alerts: {alert.settings_link}"]
    return subject[:200], "\n".join(lines)


def ascii_text(text: str) -> str:
    """GSM-friendly ASCII (one non-GSM character makes every segment 70 characters)."""
    value = str(text or "").replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    value = value.replace("·", "-").replace("…", "...")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def sms(alert: Alert) -> str:
    """The owner's text: "Callisa: New appointment - Emily Johnson +1617.... Cleaning, Tue, Oct 21 at 3 PM. <summary> <link>"."""
    head = f"Callisa: {alert.title} - {alert.caller}."
    if alert.details:
        head += " " + ", ".join(alert.details) + "."
    link = f" {alert.link}"
    with_summary = f"{head} {alert.summary}{link}" if alert.summary else ""
    text = with_summary if with_summary and len(ascii_text(with_summary)) <= SMS_MAX_CHARS else head + link
    return " ".join(ascii_text(text).split())


def sample(merchant: Any) -> Alert:
    """The "Send test alert" example."""
    return Alert(
        event=EVENT_BOOKING, title="Test alert", business=str(getattr(merchant, "business_name", "") or ""),
        who="Emily Johnson", phone="+16175550100", what="Sample booking", when="Tomorrow at 10 AM",
        summary="This is a test. Real alerts show who called, what they wanted and what happened.",
        link=portal_url("/calls"), settings_link=portal_url("/settings?tab=notifications"),
    )


__all__ = ["Alert", "SMS_MAX_CHARS", "ascii_text", "build", "email", "portal_url", "sample", "sms", "title_for"]
