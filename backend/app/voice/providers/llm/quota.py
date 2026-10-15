"""Rate-limit bookkeeping per ``provider:model`` so the router skips a model
that is out of quota *before* calling it (no wasted 429 round-trip mid-call).

Fed from response headers (``x-ratelimit-remaining-tokens``,
``x-ratelimit-reset-tokens``, ``retry-after`` …) and from failures. Process-
local by design: free-tier limits are per key, and one process serves calls.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Mapping

#: Cool-off after a 5xx / timeout before the model is tried again.
ERROR_COOLOFF_SECONDS = 15.0
#: Cool-off after a 429 that carried no reset hint.
RATE_LIMIT_COOLOFF_SECONDS = 60.0

_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def parse_duration(value: str | None) -> float | None:
    """``"2m59.56s"`` → 179.56, ``"7.66s"`` → 7.66, ``"120ms"`` → 0.12, ``"30"`` → 30."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    match = _DURATION.match(text)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds, millis = (float(g) if g else 0.0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@dataclass
class _State:
    blocked_until: float = 0.0
    remaining_tokens: int | None = None
    tokens_reset_at: float = 0.0
    remaining_requests: int | None = None
    requests_reset_at: float = 0.0
    limit_tokens: int | None = None
    limit_requests: int | None = None
    requests: int = 0
    failures: int = 0
    last_error: str = ""


class QuotaBook:
    def __init__(self, clock: Any = time.monotonic) -> None:
        self._clock = clock
        self._states: dict[str, _State] = {}

    def _state(self, key: str) -> _State:
        return self._states.setdefault(key, _State())

    def available(self, key: str, need_tokens: int = 0) -> bool:
        state = self._states.get(key)
        if state is None:
            return True
        now = self._clock()
        if now < state.blocked_until:
            return False
        if state.remaining_requests is not None and state.remaining_requests <= 0 and now < state.requests_reset_at:
            return False
        if (
            need_tokens
            and state.remaining_tokens is not None
            and state.remaining_tokens < need_tokens
            and now < state.tokens_reset_at
        ):
            return False
        return True

    def note_response(self, key: str, headers: Mapping[str, str]) -> None:
        state = self._state(key)
        now = self._clock()
        state.requests += 1
        state.failures = 0
        tokens = _int(headers.get("x-ratelimit-remaining-tokens"))
        if tokens is not None:
            state.remaining_tokens = tokens
            state.tokens_reset_at = now + (parse_duration(headers.get("x-ratelimit-reset-tokens")) or 60.0)
        state.limit_tokens = _int(headers.get("x-ratelimit-limit-tokens")) or state.limit_tokens
        state.limit_requests = _int(headers.get("x-ratelimit-limit-requests")) or state.limit_requests
        requests = _int(headers.get("x-ratelimit-remaining-requests"))
        if requests is not None:
            state.remaining_requests = requests
            state.requests_reset_at = now + (parse_duration(headers.get("x-ratelimit-reset-requests")) or 60.0)

    def note_failure(self, key: str, status: int, headers: Mapping[str, str] | None = None, error: str = "") -> None:
        state = self._state(key)
        now = self._clock()
        headers = headers or {}
        state.failures += 1
        state.last_error = error[:200]
        if status == 429:
            wait = (
                parse_duration(headers.get("retry-after"))
                or parse_duration(headers.get("x-ratelimit-reset-tokens"))
                or RATE_LIMIT_COOLOFF_SECONDS
            )
            state.blocked_until = now + max(1.0, wait)
        elif status in (401, 403):
            state.blocked_until = now + 3600.0  # bad key: don't hammer it during calls
        else:
            state.blocked_until = now + ERROR_COOLOFF_SECONDS * min(state.failures, 4)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        now = self._clock()
        return {
            key: {
                "available": now >= s.blocked_until,
                "blocked_for_s": round(max(0.0, s.blocked_until - now), 1),
                "remaining_tokens": s.remaining_tokens,
                "remaining_requests": s.remaining_requests,
                "limit_tokens": s.limit_tokens,
                "limit_requests": s.limit_requests,
                "requests": s.requests,
                "failures": s.failures,
                "last_error": s.last_error,
            }
            for key, s in self._states.items()
        }


#: Shared by every call in this process.
QUOTAS = QuotaBook()

__all__ = ["QUOTAS", "QuotaBook", "parse_duration"]
