"""Rate limiting: a pluggable-store limiter (Redis when connected, else memory),
the real client IP behind trusted proxies, and login lockouts.

- ``await rate_limit(request, "bucket", max_hits=, per_seconds=)`` — per client IP (or ``key=``).
- ``limit(...)`` — the same, synchronous, this process only (older call sites).
- ``lockout`` — sign-in throttling with growing lockouts.
"""

from app.core.ratelimit.ip import client_ip, parse_client_ip
from app.core.ratelimit.limiter import enforce, limit, rate_limit, too_many

__all__ = ["client_ip", "enforce", "limit", "parse_client_ip", "rate_limit", "too_many"]
