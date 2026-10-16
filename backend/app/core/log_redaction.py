"""Keep personal data and credentials out of the logs.

``redact_event`` is a structlog processor: string values are scrubbed of phone
numbers (last 3 digits kept), email addresses (domain kept), bearer tokens, API
keys and signed tokens; values under secret-looking keys are masked entirely.
``AccessLogFilter`` does the same for uvicorn's access log lines, whose paths can
carry calendar feed tokens and webhook signatures; ``RedactingFilter`` for every
other stdlib record (httpx request lines carry query-string tokens).
"""

from __future__ import annotations

import logging
import re
from typing import Any

MASK = "***"
_SECRET_KEYS = ("password", "secret", "token", "api_key", "apikey", "authorization", "signature", "cookie", "otp", "totp")
#: Keys whose values are never touched.
_SAFE_KEYS = frozenset({"timestamp", "level", "logger", "event_type", "method"})

_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_API_KEY = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|KEY[0-9A-Za-z_-]{20,}|AC[0-9a-f]{32}|eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)*)")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
#: "+" then 7–15 digits (spaces / dashes / dots allowed), or a bare run of 8–15 digits.
_PHONE = re.compile(r"(?<![\w+])(?:\+\d(?:[\s.-]?\d){6,14}|\d{8,15})(?!\w)")
_PATH_SECRETS = (
    (re.compile(r"(/api/public/calendar/)[^/?\s]+?(\.ics)"), r"\1" + MASK + r"\2"),
    (re.compile(r"(/telnyx/[a-z-]+(?:/[^/?\s]+)?/)[0-9a-f]{32}\b"), r"\1" + MASK),
    (re.compile(r"(/pay/)[^/?\s]{16,}"), r"\1" + MASK),
    # Our signed tokens anywhere (pay / verify links): base64url claims "." 64 hex.
    (re.compile(r"\b[A-Za-z0-9_-]{16,}\.[0-9a-f]{64}\b"), MASK),
    (
        re.compile(r"(?i)([?&](?:token|key|state|code|access_token|api_key|client_secret|secret|sig|signature|password|hub\.verify_token)=)[^&\s]+"),
        r"\1" + MASK,
    ),
)


def _phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return MASK + digits[-3:]


def scrub(text: str) -> str:
    text = _BEARER.sub(lambda m: f"{m.group(1)} {MASK}", text)
    text = _API_KEY.sub(MASK, text)
    text = _EMAIL.sub(lambda m: f"{MASK}@{m.group(1)}", text)
    for pattern, replacement in _PATH_SECRETS:
        text = pattern.sub(replacement, text)
    return _PHONE.sub(_phone, text)


def _secret_key(key: Any) -> bool:
    name = str(key).lower()
    return any(word in name for word in _SECRET_KEYS)


def _clean(value: Any, depth: int) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if depth >= 4:
        return value
    if isinstance(value, dict):
        return {key: _clean_item(key, item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_clean(item, depth + 1) for item in value)
    return value


def _clean_item(key: Any, value: Any, depth: int) -> Any:
    if key in _SAFE_KEYS:
        return value
    if _secret_key(key) and isinstance(value, str) and value:
        return MASK
    return _clean(value, depth)


def redact_event(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor (place it before the timestamper and renderer)."""
    return {key: _clean_item(key, value, 0) for key, value in event_dict.items()}


class AccessLogFilter(logging.Filter):
    """Scrubs uvicorn access-log records: ``(client, method, path, http_version, status)``."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], scrub(args[2]), *args[3:])
        return True


def install_access_log_filter() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, AccessLogFilter) for item in access.filters):
        access.addFilter(AccessLogFilter())


class RedactingFilter(logging.Filter):
    """Scrubs any stdlib record's final message (installed on the root handlers)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — a malformed record still gets logged
            return True
        cleaned = scrub(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


def install_stdlib_filter() -> None:
    """Root handlers scrub every record; httpx / httpcore request lines (full URLs) stay quiet."""
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


__all__ = ["AccessLogFilter", "RedactingFilter", "install_access_log_filter", "install_stdlib_filter", "redact_event", "scrub"]
