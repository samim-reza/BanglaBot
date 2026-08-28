"""Language support for the confirmation-call agent (Bangla + English).

One dependency-free module owns everything language-shaped so the flow, the
tools, the prompt builder and the bridge agree on it:

- ``LANGUAGE_NAMES`` — the codes a merchant may pick (``bn``, ``en``).
- ``phrase(key, language, **fields)`` — the fixed lines the backend speaks
  word for word (greeting, identity question, closing lines, ...).
- ``detect_language(text)`` — cheap script-share detector for a caller
  transcript so the bridge can follow the caller's language mid-call.
- ``spoken_amount()`` / ``bangla_number_words()`` — money read-backs
  ("দুই হাজার পাঁচশো টাকা") for backend-authored lines.
- A ``contextvars`` call locale so tool handlers can ask for the caller's
  language without threading a parameter through every signature.
"""

from __future__ import annotations

import contextvars
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

BANGLA = "bn"
ENGLISH = "en"
DEFAULT_LANGUAGE = BANGLA

LANGUAGE_NAMES: dict[str, str] = {
    "bn": "Bangla (বাংলা)",
    "en": "English",
}

# Bengali Unicode block (letters, vowel signs, digits, currency sign).
_BANGLA_CHAR_RE = re.compile(r"[ঀ-৿]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
#: Fillers and loanwords heard in Bangla conversation; never language evidence.
NEUTRAL_LATIN_WORDS = frozenset(
    {
        "ok", "okay", "ok.", "yes", "no", "yeah", "yep", "nope", "ya", "hmm", "hm", "mm",
        "hello", "hi", "hey", "ji", "jee", "ha", "haan", "na", "accha", "acha", "thik", "thank",
        "thanks", "sorry", "please", "right", "fine", "sure", "bye", "confirm", "cancel", "done",
        "cash", "delivery", "order", "sir", "madam", "bhai", "apu", "boss",
    }
)


def normalize_language(value: Any, fallback: str = DEFAULT_LANGUAGE) -> str:
    """Lower-case two-letter code, falling back when the code is unknown."""
    code = str(value or "").strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGUAGE_NAMES else fallback


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(normalize_language(code), LANGUAGE_NAMES[DEFAULT_LANGUAGE])


def normalize_supported(primary: Any, supported: Any) -> list[str]:
    """Ordered, de-duplicated supported languages with the primary first."""
    codes: list[str] = [normalize_language(primary)]
    for item in supported if isinstance(supported, (list, tuple)) else []:
        code = normalize_language(item, fallback="")
        if code and code not in codes:
            codes.append(code)
    return codes


# ---------------------------------------------------------------------------
# Fixed spoken lines (polite "আপনি" Bangla; short, because every one is TTS)
# ---------------------------------------------------------------------------

_PHRASES: dict[str, dict[str, str]] = {
    "greeting": {
        "bn": "আসসালামু আলাইকুম। আমি {business_name} থেকে বলছি।",
        "en": "Hello, this is {business_name} calling.",
    },
    "opening_question": {
        "bn": "আমি কি {customer_name}-এর সাথে কথা বলছি?",
        "en": "Am I speaking with {customer_name}?",
    },
    "identity_reask": {
        "bn": "দুঃখিত, একটু বলবেন — আপনিই কি {customer_name}?",
        "en": "Sorry, just to check — is this {customer_name}?",
    },
    "knows_person_question": {
        "bn": "এই নম্বরে {customer_name}-এর নামে আমাদের কাছে একটি অর্ডার আছে। আপনি কি ওনাকে চেনেন?",
        "en": "We have an order under the name {customer_name} for this number. Do you know them?",
    },
    "relay_line": {
        "bn": "ঠিক আছে। অনুগ্রহ করে {customer_name}-কে জানাবেন, {business_name}-এর অর্ডারটি কনফার্ম করতে আমরা আবার ফোন করব। ধন্যবাদ, ভালো থাকবেন।",
        "en": "Alright. Please let {customer_name} know that {business_name} will call again to confirm the order. Thank you, goodbye.",
    },
    "wrong_number_line": {
        "bn": "দুঃখিত, ভুল নম্বর । ভালো থাকবেন।",
        "en": "Sorry, it seems we have the wrong number. Apologies for the trouble. Goodbye.",
    },
    "address_question": {
        "bn": "আপনি অর্ডারকৃত ঠিকানা {address}। ঠিকানাটা কি ঠিক আছে?",
        "en": "Let me quickly check the delivery address — {address}. Is that correct?",
    },
    "address_reask": {
        "bn": "ঠিকানাটা কি ঠিক আছে, না বদলাতে হবে?",
        "en": "Is the address correct, or does it need to change?",
    },
    "new_address_question": {
        "bn": "ওকে। সঠিক ঠিকানাটা একটু বলবেন?",
        "en": "Alright. Could you tell me the correct address?",
    },
    "decision_reask_1": {
        "bn": "দুঃখিত, ঠিক বুঝতে পারিনি। অর্ডারটি কি রাখবেন? হ্যাঁ অথবা না বলুন।",
        "en": "Sorry, I didn't quite catch that. Would you like to keep the order? Please say yes or no.",
    },
    "decision_reask_2": {
        "bn": "একটু পরিষ্কার করে বলবেন — অর্ডারটি কনফার্ম করব, নাকি বাতিল করব?",
        "en": "Just to be clear — should I confirm the order, or cancel it?",
    },
    "closing_confirmed": {
        "bn": "ধন্যবাদ! আপনার অর্ডারটি কনফার্ম করা হলো, শীঘ্রই ডেলিভারি পাঠানো হবে। ভালো থাকবেন।",
        "en": "Thank you! Your order is confirmed and will be on its way soon. Have a good day.",
    },
    "closing_cancelled": {
        "bn": "ঠিক আছে, অর্ডারটি বাতিল করা হলো। সময় দেওয়ার জন্য ধন্যবাদ, ভালো থাকবেন।",
        "en": "Alright, the order has been cancelled. Thank you for your time, goodbye.",
    },
    "closing_unclear": {
        "bn": "ঠিক আছে। আমাদের একজন প্রতিনিধি আপনার সাথে পরে যোগাযোগ করবেন। ধন্যবাদ, ভালো থাকবেন।",
        "en": "Alright. One of our team members will get back to you later. Thank you, goodbye.",
    },
    "closing_callback": {
        "bn": "ঠিক আছে, আমরা পরে আবার ফোন করব। ধন্যবাদ, ভালো থাকবেন।",
        "en": "Alright, we will call you again later. Thank you, goodbye.",
    },
    "closing_transfer": {
        "bn": "এক মুহূর্ত অপেক্ষা করুন, আমি আপনাকে আমাদের একজন প্রতিনিধির সাথে কানেক্ট করছি।",
        "en": "One moment please, I am connecting you to one of our team members.",
    },
    "closing_transfer_callback": {
        "bn": "আমাদের একজন প্রতিনিধি শীঘ্রই আপনাকে ফোন করবেন। ধন্যবাদ, ভালো থাকবেন।",
        "en": "One of our team members will call you back shortly. Thank you, goodbye.",
    },
    "closing_dropped": {
        "bn": "মনে হচ্ছে আপনাকে শুনতে পাচ্ছি না। আমরা পরে আবার ফোন করব। ভালো থাকবেন।",
        "en": "It seems I can't hear you. We will call again later. Goodbye.",
    },
    "closing_timeout": {
        "bn": "দুঃখিত, কলের সময় শেষ হয়ে গেছে। আমাদের একজন প্রতিনিধি আপনার সাথে যোগাযোগ করবেন। ভালো থাকবেন।",
        "en": "Sorry, we are out of time on this call. One of our team members will get in touch. Goodbye.",
    },
    "still_there": {
        "bn": "হ্যালো, আপনি কি শুনতে পাচ্ছেন?",
        "en": "Hello, can you hear me?",
    },
    "recovery": {
        "bn": "দুঃখিত, শুনতে [আই নি। আবার একটু বলবেন?",
        "en": "Sorry, something went wrong on my end. Could you say that again?",
    },
    "transcription_prompt": {
        "bn": "অর্ডার কনফার্মেশনের ফোন কল। হ্যাঁ, না, জি, ঠিক আছে, বাতিল, পরে, রং নাম্বার।",
        "en": "Order confirmation phone call. Yes, no, okay, cancel, later, wrong number.",
    },
    "cash_on_delivery": {
        "bn": "ক্যাশ অন ডেলিভারি",
        "en": "cash on delivery",
    },
    # Settings page: what the agent will ask, in order.
    "preview_greeting": {
        "bn": "শুভেচ্ছা: \"{greeting}\"",
        "en": "Greeting: \"{greeting}\"",
    },
    "preview_identity": {
        "bn": "পরিচয় যাচাই: \"আমি কি (কাস্টমারের নাম)-এর সাথে কথা বলছি?\" — অন্য কেউ ধরলে জিজ্ঞেস করা হয় তিনি কাস্টমারকে চেনেন কি না।",
        "en": "Identity check: \"Am I speaking with (customer name)?\" — if someone else answers, the agent asks whether they know the customer.",
    },
    "preview_address": {
        "bn": "ঠিকানা যাচাই: ডেলিভারি ঠিকানা পড়ে শুনিয়ে জিজ্ঞেস করা হয় ঠিক আছে কি না; বদল হলে নতুন ঠিকানা নোট করা হয়।",
        "en": "Address check: the delivery address is read back and confirmed; a corrected address is noted.",
    },
    "preview_decision": {
        "bn": "অর্ডার কনফার্মেশন: পণ্য, মোট টাকা ও ক্যাশ অন ডেলিভারি বলে জিজ্ঞেস করা হয় অর্ডারটি কনফার্ম করবেন কি না। অস্পষ্ট উত্তরে সর্বোচ্চ দুইবার আবার জিজ্ঞেস করা হয়।",
        "en": "Order confirmation: the items, total amount and cash on delivery are stated and the customer is asked to confirm or cancel. Unclear answers are re-asked up to twice.",
    },
    "preview_wrap_up": {
        "bn": "সমাপ্তি: ফলাফল অনুযায়ী বিদায়বাক্য (কনফার্ম / বাতিল / পরে যোগাযোগ) বলে কল শেষ হয়।",
        "en": "Wrap-up: the matching closing line (confirmed / cancelled / follow-up) is spoken and the call ends.",
    },
    # Spoken the instant a caller turn lands, before the model has replied, so the
    # caller never hears dead air while the reply is being thought out.
    "ack": {
        "bn": "হ্যাঁ।",
        "en": "Okay.",
    },
    # Confirmation question used when the pre-composed one is unavailable.
    "decision_fallback": {
        "bn": "আপনি {items} অর্ডার করেছেন, মোট {amount}, {cod}। অর্ডারটি কি কনফার্ম করবেন?",
        "en": "You ordered {items}, total {amount}, {cod}. Would you like to confirm the order?",
    },
}

PHRASE_KEYS = tuple(_PHRASES)


def phrase(key: str, language: str | None = None, **fields: Any) -> str:
    """Fixed spoken line ``key`` in ``language``; unknown keys return ''."""
    table = _PHRASES.get(key)
    if not table:
        return ""
    lang = normalize_language(language)
    text = table.get(lang) or table.get(DEFAULT_LANGUAGE) or ""
    if fields:
        try:
            text = text.format(**fields)
        except (KeyError, IndexError, ValueError):
            pass
    return text


# ---------------------------------------------------------------------------
# Caller-language detection
# ---------------------------------------------------------------------------


def contains_bangla(text: str | None) -> bool:
    return bool(_BANGLA_CHAR_RE.search(str(text or "")))


def detect_language(text: str | None, *, supported: list[str] | tuple[str, ...] | None = None) -> str | None:
    """Best-effort language of a caller transcript, or ``None`` when unsure.

    Bengali script is unambiguous, so the decision is a script share: mostly
    Bengali letters → ``bn``; mostly Latin letters → ``en``. Mixed lines (a
    Bangla sentence with an English product name in it) still count as
    Bangla. Very short or letter-free lines ("2", "ok") return ``None`` so a
    bare number never flips the language. ``supported`` restricts the answer
    to languages the merchant enabled.
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    bangla = len(_BANGLA_CHAR_RE.findall(raw))
    # Loanwords Bangladeshi callers use in either language ("ওকে" transcribed as
    # "Okay", "yes", "hello") are no evidence of English; count only real words.
    latin_words = [w for w in _LATIN_WORD_RE.findall(raw) if w.lower() not in NEUTRAL_LATIN_WORDS]
    latin = sum(len(w) for w in latin_words)
    if bangla + latin < 3:
        return None
    share = bangla / (bangla + latin)
    if share >= 0.4:
        detected = BANGLA
    elif share <= 0.1 and len(latin_words) >= 2 and latin >= 6:
        # Switching to English takes an actual English phrase, not one word.
        detected = ENGLISH
    else:
        return None
    if supported is not None and detected not in {normalize_language(code) for code in supported}:
        return None
    return detected


# ---------------------------------------------------------------------------
# Money and numbers
# ---------------------------------------------------------------------------

_BANGLA_UNITS = (
    "শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়",
    "দশ", "এগারো", "বারো", "তেরো", "চৌদ্দ", "পনেরো", "ষোলো", "সতেরো", "আঠারো", "উনিশ",
    "বিশ", "একুশ", "বাইশ", "তেইশ", "চব্বিশ", "পঁচিশ", "ছাব্বিশ", "সাতাশ", "আটাশ", "ঊনত্রিশ",
    "ত্রিশ", "একত্রিশ", "বত্রিশ", "তেত্রিশ", "চৌত্রিশ", "পঁয়ত্রিশ", "ছত্রিশ", "সাঁইত্রিশ", "আটত্রিশ", "ঊনচল্লিশ",
    "চল্লিশ", "একচল্লিশ", "বিয়াল্লিশ", "তেতাল্লিশ", "চুয়াল্লিশ", "পঁয়তাল্লিশ", "ছেচল্লিশ", "সাতচল্লিশ", "আটচল্লিশ", "ঊনপঞ্চাশ",
    "পঞ্চাশ", "একান্ন", "বায়ান্ন", "তিপ্পান্ন", "চুয়ান্ন", "পঞ্চান্ন", "ছাপ্পান্ন", "সাতান্ন", "আটান্ন", "ঊনষাট",
    "ষাট", "একষট্টি", "বাষট্টি", "তেষট্টি", "চৌষট্টি", "পঁয়ষট্টি", "ছেষট্টি", "সাতষট্টি", "আটষট্টি", "ঊনসত্তর",
    "সত্তর", "একাত্তর", "বাহাত্তর", "তিয়াত্তর", "চুয়াত্তর", "পঁচাত্তর", "ছিয়াত্তর", "সাতাত্তর", "আটাত্তর", "ঊনআশি",
    "আশি", "একাশি", "বিরাশি", "তিরাশি", "চুরাশি", "পঁচাশি", "ছিয়াশি", "সাতাশি", "আটাশি", "ঊননব্বই",
    "নব্বই", "একানব্বই", "বিরানব্বই", "তিরানব্বই", "চুরানব্বই", "পঁচানব্বই", "ছিয়ানব্বই", "সাতানব্বই", "আটানব্বই", "নিরানব্বই",
)
_BANGLA_HUNDREDS = ("", "একশো", "দুইশো", "তিনশো", "চারশো", "পাঁচশো", "ছয়শো", "সাতশো", "আটশো", "নয়শো")


def bangla_number_words(value: int) -> str:
    """Spoken Bangla for a non-negative integer (Indian grouping: হাজার / লাখ / কোটি)."""
    number = int(value)
    if number < 0:
        return f"মাইনাস {bangla_number_words(-number)}"
    if number < 100:
        return _BANGLA_UNITS[number]
    parts: list[str] = []
    crore, number = divmod(number, 10_000_000)
    lakh, number = divmod(number, 100_000)
    thousand, number = divmod(number, 1_000)
    hundred, number = divmod(number, 100)
    if crore:
        parts.append(f"{bangla_number_words(crore)} কোটি")
    if lakh:
        parts.append(f"{bangla_number_words(lakh)} লাখ")
    if thousand:
        parts.append(f"{bangla_number_words(thousand)} হাজার")
    if hundred:
        parts.append(_BANGLA_HUNDREDS[hundred])
    if number:
        parts.append(_BANGLA_UNITS[number])
    return " ".join(parts)


_CURRENCY_WORDS: dict[str, dict[str, tuple[str, str]]] = {
    # code -> language -> (major unit, minor unit)
    "BDT": {"en": ("taka", "poisha"), "bn": ("টাকা", "পয়সা")},
    "USD": {"en": ("dollars", "cents"), "bn": ("ডলার", "সেন্ট")},
    "INR": {"en": ("rupees", "paise"), "bn": ("রুপি", "পয়সা")},
    "EUR": {"en": ("euros", "cents"), "bn": ("ইউরো", "সেন্ট")},
    "GBP": {"en": ("pounds", "pence"), "bn": ("পাউন্ড", "পেন্স")},
}


def spoken_amount(value: Any, currency: str | None = "BDT", language: str | None = None) -> str:
    """Speak a money amount the way a person would on the phone.

    Bangla + BDT: whole taka in words ("দুই হাজার পাঁচশো টাকা"), poisha only when
    non-zero. English: "2500 taka" (decimals only when non-zero).
    """
    lang = normalize_language(language)
    code = str(currency or "BDT").strip().upper() or "BDT"
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal("0.00")
    words = _CURRENCY_WORDS.get(code, {}).get(lang) or _CURRENCY_WORDS.get(code, {}).get(ENGLISH) or (code, "")
    major, minor = words
    whole = int(amount)
    fraction = int((amount - whole) * 100)
    if lang == BANGLA and code == "BDT":
        text = f"{bangla_number_words(whole)} {major}"
        if fraction and minor:
            text = f"{text} {bangla_number_words(fraction)} {minor}"
        return text
    if fraction:
        return f"{amount:.2f} {major}".strip()
    return f"{whole} {major}".strip()


# ---------------------------------------------------------------------------
# Per-call locale (language + currency) for tool handlers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallLocale:
    language: str = DEFAULT_LANGUAGE
    currency: str = "BDT"


_call_locale: contextvars.ContextVar[CallLocale] = contextvars.ContextVar("call_locale", default=CallLocale())


def set_call_locale(language: str | None, currency: str | None = None) -> contextvars.Token:
    return _call_locale.set(
        CallLocale(language=normalize_language(language), currency=str(currency or "BDT").strip().upper() or "BDT")
    )


def reset_call_locale(token: contextvars.Token) -> None:
    try:
        _call_locale.reset(token)
    except ValueError:
        _call_locale.set(CallLocale())


def call_locale() -> CallLocale:
    return _call_locale.get()


def call_language() -> str:
    return _call_locale.get().language


def call_currency() -> str:
    return _call_locale.get().currency
