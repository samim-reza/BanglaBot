"""Login throttling: per-IP and per-username rate limits plus a growing lockout
after repeated failures (1 → 5 → 15 minutes), reset by a successful login."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.ratelimit import backends
from app.core.ratelimit.ip import client_ip
from app.core.ratelimit.limiter import enforce, too_many

LOCKED_DETAIL = "Too many failed sign-in attempts — try again later."


@dataclass(frozen=True)
class LoginPolicy:
    scope: str
    #: (attempts, seconds) allowed from one IP / for one username.
    per_ip: tuple[int, int]
    per_user: tuple[int, int]
    #: (failures so far, lock seconds), ascending; the last reached step applies.
    steps: tuple[tuple[int, int], ...]
    #: Failures are forgotten this long after the first one.
    failure_ttl: int = 3600


MERCHANT_LOGIN = LoginPolicy("login", per_ip=(5, 60), per_user=(5, 60), steps=((5, 60), (10, 300), (15, 900)))
ADMIN_LOGIN = LoginPolicy("admin-login", per_ip=(3, 60), per_user=(3, 60), steps=((3, 60), (6, 300), (9, 900)))


def _user_key(username: str) -> str:
    return str(username or "").strip().lower()[:80]


def lock_seconds(policy: LoginPolicy, failures: int) -> int:
    seconds = 0
    for threshold, lock in policy.steps:
        if failures >= threshold:
            seconds = lock
    return seconds


async def before_attempt(request: Request, policy: LoginPolicy, username: str) -> None:
    """Raise 429 when this IP / username is over its limit or locked out."""
    user = _user_key(username)
    _, locked_for = await backends.call("get", f"{policy.scope}:lock:{user}")
    if locked_for > 0:
        raise too_many(locked_for, LOCKED_DETAIL)
    await enforce(f"{policy.scope}:ip:{client_ip(request)}", *policy.per_ip)
    await enforce(f"{policy.scope}:user:{user}", *policy.per_user)


async def record_failure(policy: LoginPolicy, username: str) -> int:
    """Count a failed attempt; returns the lockout (seconds) it triggered, 0 for none."""
    user = _user_key(username)
    failures = await backends.call("incr", f"{policy.scope}:fail:{user}", policy.failure_ttl)
    seconds = lock_seconds(policy, int(failures))
    if seconds:
        await backends.call("put", f"{policy.scope}:lock:{user}", 1, seconds)
    return seconds


async def record_success(policy: LoginPolicy, username: str) -> None:
    user = _user_key(username)
    await backends.call("delete", f"{policy.scope}:fail:{user}", f"{policy.scope}:lock:{user}")


__all__ = ["ADMIN_LOGIN", "MERCHANT_LOGIN", "LoginPolicy", "before_attempt", "lock_seconds", "record_failure", "record_success"]
