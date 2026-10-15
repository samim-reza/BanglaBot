"""The finance cost guard as seen by the provider chains: is this provider over today's spend cap?"""

from __future__ import annotations


def over_cap(provider: str) -> bool:
    """True when the admin's daily USD cap for ``provider`` is spent (never raises; no cap = False)."""
    try:
        from app.finance.guard import over_cap as guard_over_cap

        return bool(guard_over_cap(provider))
    except Exception:  # noqa: BLE001 — a broken guard must never take the voice down
        return False


__all__ = ["over_cap"]
