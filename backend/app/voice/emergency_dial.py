"""An emergency transfer on its way from the tools to the phone bridge.

The target travels as the utterance's ``transfer_to`` with a marker, so the bridge dials it
as an emergency call: a short code ("911") is dialled exactly as written, and when that
leg ends (or can't start) the caller hears where to dial themselves."""

from __future__ import annotations

PREFIX = "emergency:"


def mark(number: str) -> str:
    return f"{PREFIX}{number}"


def unmark(transfer_to: str) -> tuple[bool, str]:
    """``(is_emergency, number)``."""
    text = str(transfer_to or "")
    if text.startswith(PREFIX):
        return True, text[len(PREFIX):]
    return False, text


__all__ = ["PREFIX", "mark", "unmark"]
