"""Calendar links the server will fetch (busy iCal feeds): http(s)/webcal only, never a private host."""

from __future__ import annotations

from app.core.security import outbound

ICS_PREFIXES = ("https://", "http://", "webcal://")


def check_ics_url(url: str) -> str:
    """An iCal link the server may fetch (scheme + no private / internal host); ``ValueError`` otherwise."""
    if not url.lower().startswith(ICS_PREFIXES):
        raise ValueError("calendar links must start with https:// (or webcal://)")
    try:
        outbound.check_url("https://" + url[len("webcal://"):] if url.lower().startswith("webcal://") else url)
    except outbound.UnsafeURLError as exc:
        raise ValueError(f"calendar link: {exc}") from exc
    return url


__all__ = ["ICS_PREFIXES", "check_ics_url"]
