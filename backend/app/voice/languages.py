"""Language support for the call agent (English).

One dependency-free module owns everything language-shaped so the flow, the
tools, the prompt builder and the bridge agree on it:

- ``LANGUAGE_NAMES`` — the codes a merchant may pick (``en``). Any other
  stored or incoming code (an older account's) normalizes to English.
- ``phrase(key, language, **fields)`` — the fixed lines the backend speaks
  word for word (greeting, identity question, closing lines, ...).
- ``spoken_amount()`` — money read-backs ("2500 dollars") for backend-authored lines.
- A ``contextvars`` call locale so tool handlers can ask for the caller's
  language without threading a parameter through every signature.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

ENGLISH = "en"
DEFAULT_LANGUAGE = ENGLISH
DEFAULT_CURRENCY = "USD"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
}


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
# Fixed spoken lines (short, because every one is TTS)
# ---------------------------------------------------------------------------

_PHRASES: dict[str, dict[str, str]] = {
    "greeting": {"en": "Hello, this is {business_name} calling."},
    "opening_question": {"en": "Am I speaking with {customer_name}?"},
    "identity_reask": {"en": "Sorry, just to check — is this {customer_name}?"},
    "knows_person_question": {"en": "We have an order under the name {customer_name} for this number. Do you know them?"},
    "relay_line": {"en": "Alright. Please let {customer_name} know that {business_name} will call again to confirm the order. Thank you, goodbye."},
    "wrong_number_line": {"en": "Sorry, it seems we have the wrong number. Apologies for the trouble. Goodbye."},
    "address_question": {"en": "Let me quickly check the delivery address — {address}. Is that correct?"},
    "address_reask": {"en": "Is the address correct, or does it need to change?"},
    "new_address_question": {"en": "Alright. Could you tell me the correct address?"},
    "decision_reask_1": {"en": "Sorry, I didn't quite catch that. Would you like to keep the order? Please say yes or no."},
    "decision_reask_2": {"en": "Just to be clear — should I confirm the order, or cancel it?"},
    "closing_confirmed": {"en": "Thank you! Your order is confirmed and will be on its way soon. Have a good day."},
    "closing_cancelled": {"en": "Alright, the order has been cancelled. Thank you for your time, goodbye."},
    "closing_unclear": {"en": "Alright. One of our team members will get back to you later. Thank you, goodbye."},
    "closing_callback": {"en": "Alright, we will call you again later. Thank you, goodbye."},
    "closing_transfer": {"en": "One moment please, I am connecting you to one of our team members."},
    "closing_transfer_callback": {"en": "One of our team members will call you back shortly. Thank you, goodbye."},
    "closing_dropped": {"en": "It seems I can't hear you. We will call again later. Goodbye."},
    "closing_timeout": {"en": "Sorry, we are out of time on this call. One of our team members will get in touch. Goodbye."},
    "still_there": {"en": "Hello, can you hear me?"},
    # Second and later silence re-prompts (each followed by the unanswered question).
    "still_there_again": {"en": "Are you still there?"},
    "recovery": {"en": "Sorry, something went wrong on my end. Could you say that again?"},
    "unclear_1": {"en": "Sorry, I didn't catch that."},
    "unclear_2": {"en": "Sorry, could you say that once more?"},
    "unclear_3": {"en": "I'm having a little trouble hearing you."},
    "anything_else": {"en": "Is there anything else I can help you with?"},
    "closing_saved": {"en": "All set — that's saved."},
    "closing_caller_later": {"en": "No problem — call us back whenever suits you. Goodbye."},
    "detail_why": {"en": "No problem — it just helps us keep your booking straight."},
    "detail_skipped": {"en": "No problem, we'll go ahead without it."},
    "transcription_prompt": {"en": "Phone call. Yes, no, okay, sure, cancel, later, wrong number."},
    "cash_on_delivery": {"en": "cash on delivery"},
    # --- inbound / business engines -------------------------------------
    "greeting_inbound": {"en": "Hello, thank you for calling {business_name}."},
    "greeting_chat": {"en": "Hi, welcome to {business_name}!"},
    "how_can_i_help": {"en": "How can I help you today?"},
    "ask_caller_name": {"en": "May I have your name, please?"},
    "ask_phone": {"en": "What's the best mobile number to reach you?"},
    "phone_invalid": {"en": "Sorry, I didn't get the number. Could you say it again slowly, digit by digit?"},
    "amend_question": {"en": "Alright. What should I change?"},
    "closing_inquiry": {"en": "Thank you for calling. Goodbye."},
    "closing_lead": {"en": "Thank you. One of our team will get in touch with you shortly. Goodbye."},
    "closing_not_interested": {"en": "Alright, thank you for your time. Goodbye."},
    "emergency_line": {"en": "This sounds like an emergency. Please call {emergency} right now."},
    "emergency_offer": {"en": "Would you like me to connect you to {target} now?"},
    "emergency_connecting": {"en": "Connecting you now. Tell them your exact address right away."},
    "emergency_after_dial": {"en": "If you still need help, hang up and dial {emergency} now."},
    "emergency_not_connected": {"en": "I couldn't connect the call. Please hang up and dial {emergency} right now."},
    "emergency_goodbye": {"en": "Okay. Please stay safe, and call {emergency} if you need help. Goodbye."},
    "sms_follows": {"en": "We'll text you the details."},
    "confirm_reprompt": {"en": "So, shall I go ahead and confirm it?"},
    "yes_no_reask_1": {"en": "Sorry, I didn't quite catch that. Could you say yes or no?"},
    "yes_no_reask_2": {"en": "Just to be clear — yes, or no?"},
    "working": {"en": "Let me check that."},
    # Settings page: what the agent will ask, in order.
    "preview_greeting": {"en": "Greeting: \"{greeting}\""},
    "preview_identity": {
        "en": "Identity check: \"Am I speaking with (customer name)?\" — if someone else answers, the agent asks whether they know the customer.",
    },
    "preview_address": {"en": "Address check: the delivery address is read back and confirmed; a corrected address is noted."},
    "preview_decision": {
        "en": "Order confirmation: the items, total amount and cash on delivery are stated and the customer is asked to confirm or cancel. Unclear answers are re-asked up to twice.",
    },
    "preview_wrap_up": {"en": "Wrap-up: the matching closing line (confirmed / cancelled / follow-up) is spoken and the call ends."},
    # Spoken the instant a caller turn lands, before the model has replied, so the
    # caller never hears dead air while the reply is being thought out.
    "ack": {"en": "Okay."},
    # Confirmation question used when the pre-composed one is unavailable.
    "decision_fallback": {"en": "You ordered {items}, total {amount}, {cod}. Would you like to confirm the order?"},
}

PHRASE_KEYS = tuple(_PHRASES)

#: Instant acknowledgements, rotated so a long call never sounds like a loop.
_ACKS: dict[str, tuple[str, ...]] = {
    "en": ("Okay.", "Sure.", "Alright.", "Got it."),
}


def ack_lines(language: str | None = None) -> tuple[str, ...]:
    return _ACKS.get(normalize_language(language), _ACKS[DEFAULT_LANGUAGE])


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
# Money
# ---------------------------------------------------------------------------

_CURRENCY_WORDS: dict[str, tuple[str, str]] = {
    # code -> (major unit, minor unit)
    "USD": ("dollars", "cents"),
    "INR": ("rupees", "paise"),
    "EUR": ("euros", "cents"),
    "GBP": ("pounds", "pence"),
    "CAD": ("dollars", "cents"),
    "AUD": ("dollars", "cents"),
    "NZD": ("dollars", "cents"),
    "SGD": ("dollars", "cents"),
    "AED": ("dirhams", "fils"),
    "PKR": ("rupees", "paisa"),
    "ZAR": ("rand", "cents"),
    "NGN": ("naira", "kobo"),
}


def spoken_amount(value: Any, currency: str | None = DEFAULT_CURRENCY, language: str | None = None) -> str:
    """Speak a money amount the way a person would on the phone: "2500 dollars"
    (minor units only when non-zero). ``language`` is accepted for symmetry."""
    code = str(currency or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal("0.00")
    major, minor = _CURRENCY_WORDS.get(code) or (code, "")
    whole = int(amount)
    fraction = int((amount - whole) * 100)
    if fraction:
        # "89 pounds and 50 pence" — a TTS voice reads "89.50 pounds" digit by digit.
        return f"{whole} {major} and {fraction} {minor}".strip() if minor else f"{amount:.2f} {major}".strip()
    return f"{whole} {major}".strip()


# ---------------------------------------------------------------------------
# Per-call locale (language + currency) for tool handlers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallLocale:
    language: str = DEFAULT_LANGUAGE
    currency: str = DEFAULT_CURRENCY


_call_locale: contextvars.ContextVar[CallLocale] = contextvars.ContextVar("call_locale", default=CallLocale())


def set_call_locale(language: str | None, currency: str | None = None) -> contextvars.Token:
    return _call_locale.set(
        CallLocale(language=normalize_language(language), currency=str(currency or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY)
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
