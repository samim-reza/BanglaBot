"""The summary request and its answer, pure (no I/O): which conversations get one, the
facts + transcript the model reads, and the cleanup of what it writes."""

from __future__ import annotations

import re
from typing import Any

#: Long conversations are cut to this many transcript characters (head + tail kept).
MAX_TRANSCRIPT_CHARS = 6000
HEAD_CHARS = 1500
#: A stored summary never exceeds this (a runaway answer is cut at a sentence end).
MAX_SUMMARY_CHARS = 400

SYSTEM_PROMPT = (
    "You summarize one phone call or chat between a business's AI receptionist and a customer, for the business owner. "
    "Write one or two short, plain sentences: who it was (their name if known), what they wanted, what happened "
    "(what was booked, answered or taken down, with the key date, time or reference), and any follow-up the business "
    "needs to do (for example a call back). Use only facts from the conversation. Past tense. No greeting, no lists, "
    "no markdown, no quotes, at most 45 words."
)

CHANNELS = {
    "inbound": "Phone call (customer called in)",
    "outbound": "Phone call (business called the customer)",
    "web": "Test call from the portal",
    "chat": "Test chat from the portal",
    "widget": "Website chat",
    "whatsapp": "WhatsApp chat",
    "messenger": "Facebook Messenger chat",
    "instagram": "Instagram chat",
}

_CUSTOMER_LINE = re.compile(r"^\s*(customer|caller|visitor|user)\s*:\s*\S", re.IGNORECASE | re.MULTILINE)


def has_caller_turn(transcript: str | None) -> bool:
    """True when the customer said / wrote at least one thing."""
    return bool(_CUSTOMER_LINE.search(str(transcript or "")))


def excerpt(transcript: str, limit: int = MAX_TRANSCRIPT_CHARS) -> str:
    """The transcript, or its start and end when it is long (the outcome is usually at the end)."""
    text = str(transcript or "").strip()
    if len(text) <= limit:
        return text
    head = text[:HEAD_CHARS].rsplit("\n", 1)[0]
    tail = text[-(limit - len(head)):].split("\n", 1)[-1]
    return f"{head}\n[...]\n{tail}"


def facts(
    *, business: str = "", direction: str = "", caller_number: str = "", outcome: str = "", record: Any = None,
    when: str = "", amount: str = "", item_name: str = "",
) -> list[str]:
    """``Key: value`` lines the model may rely on (only the ones known)."""
    lines = [f"Business: {business}" if business else "", f"Channel: {CHANNELS.get(direction, direction)}" if direction else ""]
    if caller_number:
        lines.append(f"Caller number: {caller_number}")
    if outcome:
        lines.append(f"Result recorded by the receptionist: {outcome.replace('_', ' ')}")
    if record is not None:
        name = str(getattr(record, "customer_name", "") or "")
        if name and name.lower() != "caller":
            lines.append(f"Customer name: {name}")
        what = str(getattr(record, "items_summary", "") or "") or item_name
        kind = str(getattr(record, "kind", "") or "record")
        if what:
            lines.append(f"{kind.capitalize()}: {what}")
        if when:
            lines.append(f"When: {when}")
        if amount:
            lines.append(f"Total: {amount}")
        ref = str(getattr(record, "order_ref", "") or "")
        if ref:
            lines.append(f"Reference: {ref}")
    return [line for line in lines if line]


def build_messages(fact_lines: list[str], transcript: str) -> list[dict[str, str]]:
    body = "\n".join(fact_lines)
    user = (body + "\n\n" if body else "") + "Conversation:\n" + excerpt(transcript)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


_MARKDOWN = re.compile(r"[*_#`>]+")
_PREFIX = re.compile(r"^\s*(summary|call summary|chat summary)\s*[:\-]\s*", re.IGNORECASE)


def clean(text: str | None) -> str:
    """The model's answer as one plain line (no markdown, labels or wrapping quotes), capped."""
    value = _MARKDOWN.sub("", str(text or ""))
    value = " ".join(value.split()).strip("\"' ")
    value = _PREFIX.sub("", value).strip("\"' ")
    if len(value) <= MAX_SUMMARY_CHARS:
        return value
    cut = value[:MAX_SUMMARY_CHARS]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 40 else cut.rsplit(" ", 1)[0].rstrip(",;:") + "..."


__all__ = ["CHANNELS", "MAX_SUMMARY_CHARS", "SYSTEM_PROMPT", "build_messages", "clean", "excerpt", "facts", "has_caller_turn"]
