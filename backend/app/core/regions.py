"""Region presets for accounts: clock, money, emergency number, phone format, accent.

The admin picks a region when creating an account; its values are copied onto
the account (timezone, currency, emergency_number) and stay editable there.
The region itself keeps deciding the phone-number format and the English
accent of the voice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Region:
    code: str
    label: str
    timezone: str
    currency: str
    emergency: str
    #: Country calling code without "+" ("" = numbers must be dialed in +E.164).
    calling_code: str = ""
    #: National trunk prefix dropped when adding the country code ("0" in the UK).
    trunk_prefix: str = "0"
    #: Azure English voice locale.
    accent: str = "en-US"
    #: "mdy" = "October 12" (US style), "dmy" = "12 October".
    date_style: str = "dmy"
    #: Default working days for new accounts.
    working_days: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat")
    #: Free health-advice line the clinic agent may suggest (never for emergencies).
    health_line: str = ""
    #: National number lengths (digits without trunk prefix / country code) a mobile number has.
    national_lengths: tuple[int, ...] = field(default_factory=tuple)


REGIONS: dict[str, Region] = {
    region.code: region
    for region in (
        Region("INTL", "International", "UTC", "USD", "112", accent="en-US"),
        Region("US", "United States", "America/New_York", "USD", "911", "1", "", "en-US", "mdy", national_lengths=(10,)),
        Region("CA", "Canada", "America/Toronto", "CAD", "911", "1", "", "en-CA", "mdy", national_lengths=(10,)),
        Region("GB", "United Kingdom", "Europe/London", "GBP", "999", "44", "0", "en-GB", "dmy", health_line="111 (NHS)", national_lengths=(10,)),
        Region("IE", "Ireland", "Europe/Dublin", "EUR", "112", "353", "0", "en-IE", "dmy", national_lengths=(9,)),
        Region("AU", "Australia", "Australia/Sydney", "AUD", "000", "61", "0", "en-AU", "dmy", health_line="1800 022 222 (healthdirect)", national_lengths=(9,)),
        Region("NZ", "New Zealand", "Pacific/Auckland", "NZD", "111", "64", "0", "en-NZ", "dmy", health_line="0800 611 116 (Healthline)", national_lengths=(8, 9, 10)),
        Region("IN", "India", "Asia/Kolkata", "INR", "112", "91", "0", "en-IN", "dmy", national_lengths=(10,)),
        Region(
            "BD", "Bangladesh", "Asia/Dhaka", "BDT", "999", "880", "0", "en-IN", "dmy",
            working_days=("sat", "sun", "mon", "tue", "wed", "thu"),
            health_line="16263 (Shasthyo Batayon)",
            national_lengths=(10,),
        ),
        Region("PK", "Pakistan", "Asia/Karachi", "PKR", "1122", "92", "0", "en-IN", "dmy", national_lengths=(10,)),
        Region("AE", "United Arab Emirates", "Asia/Dubai", "AED", "999", "971", "0", "en-US", "dmy",
               working_days=("mon", "tue", "wed", "thu", "fri", "sat"), national_lengths=(9,)),
        Region("SG", "Singapore", "Asia/Singapore", "SGD", "995", "65", "", "en-SG", "dmy", national_lengths=(8,)),
        Region("ZA", "South Africa", "Africa/Johannesburg", "ZAR", "112", "27", "0", "en-ZA", "dmy", national_lengths=(9,)),
        Region("NG", "Nigeria", "Africa/Lagos", "NGN", "112", "234", "0", "en-NG", "dmy", national_lengths=(10,)),
    )
}
DEFAULT_REGION = "INTL"


def get_region(code: Any) -> Region:
    return REGIONS.get(str(code or "").strip().upper(), REGIONS[DEFAULT_REGION])


def region_of(merchant: Any) -> Region:
    return get_region(getattr(merchant, "region", None))


def region_defaults(code: Any) -> dict[str, str]:
    """Account columns a region preset fills in."""
    region = get_region(code)
    return {"region": region.code, "timezone": region.timezone, "currency": region.currency, "emergency_number": region.emergency}


def normalize_phone(phone: Any, region: Region | str | None = None) -> str:
    """Local / spoken / pasted number → +E.164 for dialing (best effort).

    ``+44 7700 900123`` / ``0044…`` pass through; a national number gets the
    region's country code with its trunk prefix dropped (``07700 900123`` →
    ``+447700900123``, ``01712345678`` → ``+8801712345678``, ``(415) 555-0100``
    → ``+14155550100``).
    """
    reg = region if isinstance(region, Region) else get_region(region)
    raw = str(phone or "").strip()
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("+"):
        return "+" + re.sub(r"\D", "", cleaned[1:])
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return raw
    if digits.startswith("00"):
        return "+" + digits[2:]
    code = reg.calling_code
    if not code:
        # International accounts: a bare number is assumed to carry its country code.
        return "+" + digits
    if digits.startswith(code) and len(digits) > len(code) + 6:
        rest = digits[len(code):]
        if not reg.national_lengths or len(rest) in reg.national_lengths or len(rest) - len(reg.trunk_prefix) in reg.national_lengths:
            return "+" + code + (rest[len(reg.trunk_prefix):] if reg.trunk_prefix and rest.startswith(reg.trunk_prefix) else rest)
    if reg.trunk_prefix and digits.startswith(reg.trunk_prefix):
        digits = digits[len(reg.trunk_prefix):]
    return f"+{code}{digits}"


def regions_json() -> list[dict[str, Any]]:
    return [
        {
            "code": region.code,
            "label": region.label,
            "timezone": region.timezone,
            "currency": region.currency,
            "emergency": region.emergency,
            "calling_code": region.calling_code,
            "working_days": list(region.working_days),
        }
        for region in REGIONS.values()
    ]


__all__ = ["DEFAULT_REGION", "REGIONS", "Region", "get_region", "normalize_phone", "region_defaults", "region_of", "regions_json"]
