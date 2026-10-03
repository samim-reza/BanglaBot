"""Dates and times the way a caller says and hears them (Bangla + English).

Pure helpers, no I/O:

- ``business_tz`` / ``local_now``   — the business clock (Asia/Dhaka by default)
- ``parse_date`` / ``parse_time``   — what the model saved ("2026-10-12", "18:20")
- ``date_phrase`` / ``time_phrase`` — what the agent says ("আগামীকাল", "সন্ধ্যা ৬টা ২০ মিনিটে")
- ``calendar_facts``                — the next two weeks, so the model can turn
  "পরশু" / "next Saturday" into an ISO date without guessing
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Iterable

DEFAULT_TIMEZONE = "Asia/Dhaka"
#: Bangladesh has had no daylight saving since 2009, so a fixed +06:00 is an
#: exact fallback when the system has no tz database.
_DHAKA_FALLBACK = timezone(timedelta(hours=6), "Asia/Dhaka")

#: ``datetime.weekday()`` order.
WEEKDAY_KEYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_BN = {
    "sat": "শনিবার", "sun": "রবিবার", "mon": "সোমবার", "tue": "মঙ্গলবার",
    "wed": "বুধবার", "thu": "বৃহস্পতিবার", "fri": "শুক্রবার",
}
WEEKDAY_SHORT_BN = {
    "sat": "শনি", "sun": "রবি", "mon": "সোম", "tue": "মঙ্গল", "wed": "বুধ", "thu": "বৃহস্পতি", "fri": "শুক্র",
}
WEEKDAY_EN = {
    "sat": "Saturday", "sun": "Sunday", "mon": "Monday", "tue": "Tuesday",
    "wed": "Wednesday", "thu": "Thursday", "fri": "Friday",
}
#: Saturday-first, the Bangladeshi working week, for listing days.
WEEK_ORDER: tuple[str, ...] = ("sat", "sun", "mon", "tue", "wed", "thu", "fri")
#: Monday-first, everywhere else.
WEEK_ORDER_MON: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MONTH_BN = (
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
)
MONTH_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def bn_digits(value: Any) -> str:
    return str(value).translate(_BN_DIGITS)


def ascii_digits(value: Any) -> str:
    return str(value or "").translate(_ASCII_DIGITS)


# ---------------------------------------------------------------- the clock
def business_tz(name: str | None = None) -> tzinfo:
    key = str(name or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(key)
    except Exception:  # noqa: BLE001 — no tz database: Dhaka is a fixed offset
        return _DHAKA_FALLBACK


def local_now(tz: tzinfo | None = None) -> datetime:
    return datetime.now(timezone.utc).astimezone(tz or business_tz())


def weekday_key(day: date) -> str:
    return WEEKDAY_KEYS[day.weekday()]


def normalize_days(values: Iterable[Any] | None) -> list[str]:
    """``["Sat", "monday", "শুক্র"]`` → ``["sat", "mon", "fri"]`` (week order, no repeats)."""
    wanted: set[str] = set()
    for raw in values or []:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        for key in WEEKDAY_KEYS:
            if text.startswith(key) or text in (WEEKDAY_EN[key].lower(), WEEKDAY_BN[key], WEEKDAY_SHORT_BN[key]):
                wanted.add(key)
                break
    return [key for key in WEEK_ORDER if key in wanted]


# ---------------------------------------------------------------- parsing
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?$")
_RELATIVE_DAYS = {
    "today": 0, "আজ": 0, "aaj": 0, "aj": 0,
    "tomorrow": 1, "আগামীকাল": 1, "কাল": 1, "kal": 1, "kalke": 1,
    "day after tomorrow": 2, "পরশু": 2, "porshu": 2,
}


def parse_date(value: Any, today: date | None = None) -> date | None:
    """An ISO date (what the model is told to send), or a bare relative word."""
    text = ascii_digits(value).strip().lower()
    if not text:
        return None
    match = _ISO_DATE_RE.match(text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    if today is not None:
        if text in _RELATIVE_DAYS:
            return today + timedelta(days=_RELATIVE_DAYS[text])
        days = normalize_days([text])
        if days:
            target = WEEKDAY_KEYS.index(days[0])
            return today + timedelta(days=(target - today.weekday()) % 7 or 7)
    return None


def parse_time(value: Any) -> time | None:
    """``"18:20"`` / ``"6:20 pm"`` / ``"9"`` → ``time``; anything else → None."""
    text = ascii_digits(value).strip().lower().replace(".", ":") if value is not None else ""
    text = text.replace(" ", "")
    match = _TIME_RE.match(text.replace("::", ":"))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    meridiem = (match.group(3) or "").replace(".", "")
    if meridiem.startswith("p") and hour < 12:
        hour += 12
    elif meridiem.startswith("a") and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


# ---------------------------------------------------------------- parts of the day
#: (key, first hour inclusive, Bangla word, English word). Hours wrap at night.
PARTS_OF_DAY: tuple[tuple[str, int, str, str], ...] = (
    ("dawn", 4, "ভোর", "early morning"),
    ("morning", 6, "সকাল", "morning"),
    ("noon", 12, "দুপুর", "midday"),
    ("afternoon", 15, "বিকেল", "afternoon"),
    ("evening", 18, "সন্ধ্যা", "evening"),
    ("night", 20, "রাত", "night"),
)
#: A caller's "in the morning" etc. as a target time for picking the nearest slot.
PART_TARGETS: dict[str, time] = {
    "morning": time(9, 0), "noon": time(12, 30), "afternoon": time(15, 30),
    "evening": time(18, 30), "night": time(20, 30), "dawn": time(5, 0),
}


def part_of_day(t: time) -> str:
    current = "night"
    for key, first_hour, _bn, _en in PARTS_OF_DAY:
        if t.hour >= first_hour:
            current = key
    if t.hour < PARTS_OF_DAY[0][1]:
        return "night"
    return current


def _part_word(key: str, lang: str) -> str:
    for part, _hour, bn, en in PARTS_OF_DAY:
        if part == key:
            return bn if lang == "bn" else en
    return ""


# ---------------------------------------------------------------- speaking
def date_phrase(day: date, today: date | None = None, lang: str = "bn", *, month_first: bool = False) -> str:
    """``আজ`` / ``আগামীকাল`` / ``পরশু`` for the next days, else ``শনিবার, বারো অক্টোবর``
    (English: "tomorrow, Sunday" / "Monday, 12 October", or "Monday, October 12" month-first)."""
    if today is not None:
        delta = (day - today).days
        if lang == "bn":
            near = {0: "আজ", 1: "আগামীকাল", 2: "পরশু"}.get(delta)
            if near:
                return f"{near}, {WEEKDAY_BN[weekday_key(day)]}"
        else:
            near = {0: "today", 1: "tomorrow"}.get(delta)
            if near:
                return f"{near}, {WEEKDAY_EN[weekday_key(day)]}"
    if lang == "bn":
        return f"{WEEKDAY_BN[weekday_key(day)]}, {bn_number(day.day)} {MONTH_BN[day.month - 1]}"
    if month_first:
        return f"{WEEKDAY_EN[weekday_key(day)]}, {MONTH_EN[day.month - 1]} {day.day}"
    return f"{WEEKDAY_EN[weekday_key(day)]}, {day.day} {MONTH_EN[day.month - 1]}"


def bn_number(value: int) -> str:
    """Bangla number words (TTS reads words reliably; digits are hit-and-miss)."""
    from app.voice.languages import bangla_number_words

    return bangla_number_words(int(value))


def spoken_digits(value: Any, lang: str = "bn") -> str:
    """A phone number read digit by digit in groups (``01712345678`` → "zero one seven one two,
    three four five, six seven eight"; ``4155550100`` → "four one five, five five five, zero one zero zero")."""
    raw = ascii_digits(value).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    words_bn = ("শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়")
    words_en = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
    words = words_bn if lang == "bn" else words_en
    prefix: list[str] = []
    international = raw.startswith("+") or (len(digits) == 11 and digits.startswith("1"))
    if international:
        for code in ("880", "971", "353", "234", "1", "44", "61", "64", "91", "92", "65", "27"):
            if digits.startswith(code) and len(digits) - len(code) >= 7:
                prefix, digits = [code], digits[len(code):]
                break
    if len(digits) == 11 and digits.startswith("0"):
        groups = [digits[:5], digits[5:8], digits[8:]]
    elif len(digits) == 10:
        groups = [digits[:3], digits[3:6], digits[6:]]
    elif len(digits) <= 4:
        groups = [digits]
    else:
        groups = [digits[i : i + 3] for i in range(0, len(digits) - 4, 3)]
        tail_start = sum(len(g) for g in groups)
        groups.append(digits[tail_start:])
    spoken = ", ".join(" ".join(words[int(d)] for d in group) for group in prefix + groups)
    if raw.startswith("+"):
        spoken = ("প্লাস " if lang == "bn" else "plus ") + spoken
    return spoken


def short_number(value: Any, lang: str = "bn") -> str:
    """A short service number (911, 999, 112) the way people say it: digit by digit.
    Bangla callers say these in English digits ("নাইন নাইন নাইন")."""
    digits = re.sub(r"\D", "", ascii_digits(value))
    if lang == "bn":
        names = ("জিরো", "ওয়ান", "টু", "থ্রি", "ফোর", "ফাইভ", "সিক্স", "সেভেন", "এইট", "নাইন")
    else:
        names = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
    return " ".join(names[int(d)] for d in digits)


def snap_weekday(day: date, said: str, today: date) -> date:
    """The model sometimes turns a bare "Saturday" into the one a week later.

    When the caller's words name the weekday of ``day`` without "next"/"পরের", the
    nearest coming such day is meant (today's weekday is left alone — "Friday"
    said on a Friday is ambiguous)."""
    text = f" {str(said or '').lower()} "
    key = weekday_key(day)
    names = (WEEKDAY_EN[key].lower(), WEEKDAY_EN[key][:3].lower() + " ", WEEKDAY_BN[key], WEEKDAY_SHORT_BN[key] + "বার")
    if not any(name in text for name in names):
        return day
    if any(word in text for word in (" next ", " following ", "পরের", "আগামী সপ্তাহ")):
        return day
    delta = (day - today).days
    if delta <= 7:
        return day
    nearest = today + timedelta(days=(day.weekday() - today.weekday()) % 7)
    return nearest if nearest > today else day


_RELATIVE_PATTERNS: tuple[tuple[str, int], ...] = (
    ("day after tomorrow", 2), ("পরশু", 2), ("porshu", 2),
    ("tomorrow", 1), ("আগামীকাল", 1), ("আগামী কাল", 1), ("কালকে", 1), ("kalke", 1),
    ("today", 0), ("tonight", 0), ("আজকে", 0), ("আজ", 0),
)


def date_from_text(text: Any, today: date) -> date | None:
    """The one day a caller named ("tomorrow", "on Wednesday", "পরের শনিবার"), or None.

    A backstop for when the model leaves the date out: only an unambiguous single
    mention counts (two different days → None)."""
    lowered = f" {str(text or '').lower()} "
    lowered = re.sub(r"[^\w\s\u0980-\u09FF]", " ", lowered)
    found: set[date] = set()
    for word, offset in _RELATIVE_PATTERNS:
        if f" {word} " in lowered or (word in ("আজ", "কালকে", "আজকে", "পরশু") and f" {word}" in lowered):
            found.add(today + timedelta(days=offset))
            break
    if not found and " কাল " in lowered and "গতকাল" not in lowered:
        found.add(today + timedelta(days=1))
    for key in WEEKDAY_KEYS:
        names = (WEEKDAY_EN[key].lower(), WEEKDAY_BN[key], f"{WEEKDAY_SHORT_BN[key]}বার")
        if any(f" {name}" in lowered for name in names):
            if any(f" {word} " in lowered for word in ("next", "পরের", "আগামী সপ্তাহের")):
                # "next Wednesday" = the Wednesday of next calendar week.
                next_monday = today + timedelta(days=7 - today.weekday())
                day = next_monday + timedelta(days=WEEKDAY_KEYS.index(key))
            else:
                day = today + timedelta(days=(WEEKDAY_KEYS.index(key) - today.weekday()) % 7 or 7)
            found.add(day)
    return found.pop() if len(found) == 1 else None


def short_date_phrase(day: date, today: date, lang: str = "bn", *, month_first: bool = False) -> str:
    """For lists of options: "tomorrow" / "Tuesday" (this week) / "Tuesday, October 13"."""
    delta = (day - today).days
    if lang == "bn":
        near = {0: "আজ", 1: "আগামীকাল", 2: "পরশু"}.get(delta)
        if near:
            return near
        if 0 < delta < 7:
            return WEEKDAY_BN[weekday_key(day)]
        return date_phrase(day, None, lang)
    near = {0: "today", 1: "tomorrow"}.get(delta)
    if near:
        return near
    if 0 < delta < 7:
        return WEEKDAY_EN[weekday_key(day)]
    return date_phrase(day, None, lang, month_first=month_first)


def _bn_clock(t: time) -> tuple[str, bool]:
    """The spoken Bangla clock reading and whether it ends in a bare ``টা``."""
    hour12 = t.hour % 12 or 12
    nxt = hour12 % 12 + 1
    minute = t.minute
    if minute == 0:
        return f"{bn_number(hour12)}টা", True
    if minute == 30:
        if hour12 == 1:
            return "দেড়টা", True
        if hour12 == 2:
            return "আড়াইটা", True
        return f"সাড়ে {bn_number(hour12)}টা", True
    if minute == 15:
        return f"সোয়া {bn_number(hour12)}টা", True
    if minute == 45:
        return f"পৌনে {bn_number(nxt)}টা", True
    return f"{bn_number(hour12)}টা {bn_number(minute)} মিনিট", False


def time_phrase(t: time, lang: str = "bn", *, at: bool = False) -> str:
    """``সন্ধ্যা ৬টা ২০ মিনিট`` (``at=True`` → ``…মিনিটে`` / ``সকাল ১০টায়``) or ``6:20 PM``."""
    if lang == "bn":
        clock, bare = _bn_clock(t)
        word = _part_word(part_of_day(t), "bn")
        text = f"{word} {clock}"
        if at:
            text = f"{text}য়" if bare else f"{text}ে"
        return text
    hour12 = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    clock = f"{hour12} {suffix}" if t.minute == 0 else f"{hour12}:{t.minute:02d} {suffix}"
    return f"at {clock}" if at else clock


def days_phrase(days: Iterable[str], lang: str = "bn", *, saturday_first: bool | None = None) -> str:
    """``শনি, সোম ও বুধবার`` / ``Monday, Wednesday and Saturday`` (Saturday-first for Bangla by default)."""
    if saturday_first is None:
        saturday_first = lang == "bn"
    order = WEEK_ORDER if saturday_first else WEEK_ORDER_MON
    keys = [key for key in order if key in set(days)]
    if not keys:
        return ""
    if len(keys) == 7:
        return "প্রতিদিন" if lang == "bn" else "every day"
    if len(keys) >= 3:
        start = order.index(keys[0])
        if keys == list(order[start : start + len(keys)]):
            # A run of days: "Monday to Saturday" / "শনি থেকে বৃহস্পতিবার".
            if lang == "bn":
                return f"{WEEKDAY_SHORT_BN[keys[0]]} থেকে {WEEKDAY_BN[keys[-1]]}"
            return f"{WEEKDAY_EN[keys[0]]} to {WEEKDAY_EN[keys[-1]]}"
    if lang == "bn":
        names = [WEEKDAY_SHORT_BN[key] for key in keys]
        if len(names) == 1:
            return WEEKDAY_BN[keys[0]]
        return f"{', '.join(names[:-1])} ও {names[-1]}বার"
    names = [WEEKDAY_EN[key] for key in keys]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def calendar_facts(today: date, now: time | None = None, *, days: int = 14) -> str:
    """Compact two-week calendar for the system prompt (always English + ISO)."""
    head = f"Today is {WEEKDAY_EN[weekday_key(today)]} {today.isoformat()}"
    if now is not None:
        head += f", current time {now.strftime('%H:%M')}"
    rows = [
        f"{WEEKDAY_EN[weekday_key(today + timedelta(days=offset))][:3]} {(today + timedelta(days=offset)).isoformat()}"
        for offset in range(1, days + 1)
    ]
    return f"{head}. Next days: " + ", ".join(rows) + "."


__all__ = [
    "DEFAULT_TIMEZONE",
    "MONTH_BN",
    "MONTH_EN",
    "PART_TARGETS",
    "WEEKDAY_BN",
    "WEEKDAY_EN",
    "WEEKDAY_KEYS",
    "WEEK_ORDER",
    "ascii_digits",
    "bn_digits",
    "bn_number",
    "business_tz",
    "calendar_facts",
    "date_phrase",
    "days_phrase",
    "local_now",
    "normalize_days",
    "parse_date",
    "parse_time",
    "part_of_day",
    "short_date_phrase",
    "snap_weekday",
    "date_from_text",
    "short_number",
    "spoken_digits",
    "time_phrase",
    "weekday_key",
]
