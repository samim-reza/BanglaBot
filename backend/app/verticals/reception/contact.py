"""Reaching the caller: a spoken / typed phone number as digits, and the number to call back on.

Shared by every engine and the skill library, so this module (and the package's
top level) imports nothing heavier than the call context.
"""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext

PHONE_HINT = "Digits only, as the caller said them; keep a leading + and the country code if they gave one."


def clean_phone(value: Any) -> str:
    """A spoken / typed phone number as digits (with a leading + kept); '' when it cannot be one."""
    from app.flows.timefmt import ascii_digits

    text = ascii_digits(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not 7 <= len(digits) <= 15:
        return ""
    return f"+{digits}" if text.startswith("+") else digits


def caller_phone(slots: dict[str, Any], ctx: CallContext) -> str:
    return str(slots.get("phone") or clean_phone(ctx.caller_number) or "")


__all__ = ["PHONE_HINT", "caller_phone", "clean_phone"]
