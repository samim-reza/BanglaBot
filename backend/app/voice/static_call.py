"""Static (no-AI) confirmation call: spoken summary + keypad answers.

Used when the merchant's voice tier is "static". Instead of connecting the
media-stream agent, the TwiML endpoint speaks the order summary with Twilio's
built-in Bengali voice and gathers one DTMF digit:
1 = confirm, 2 = cancel, 3 = talk to a human (only offered when the merchant
has a support number). No input re-prompts once, then hangs up (the status
callback then settles the order to needs_review as usual).
"""

from twilio.twiml.voice_response import Gather, VoiceResponse

from app.core.config import get_settings
from app.models import Merchant, Order

MAX_PROMPT_ATTEMPTS = 2


def _say(node, text: str) -> None:
    settings = get_settings()
    node.say(text, language="bn-IN", voice=settings.twilio_say_voice)


def prompt_text(order: Order, merchant: Merchant) -> str:
    amount = f"{order.total_amount:g}"
    opening = (
        merchant.custom_greeting.strip()
        or f"আসসালামু আলাইকুম। {merchant.business_name} থেকে বলছি।"
    )
    lines = [
        opening,
        f"{order.customer_name}, আপনার অর্ডার"
        + (f" {order.items_summary}," if order.items_summary else "")
        + f" মোট {amount} টাকা, ক্যাশ অন ডেলিভারি।",
        "অর্ডারটি নিশ্চিত করতে ১ চাপুন। বাতিল করতে ২ চাপুন।",
    ]
    if merchant.support_phone:
        lines.append("প্রতিনিধির সাথে কথা বলতে ৩ চাপুন।")
    return " ".join(lines)


def build_prompt_twiml(order: Order, merchant: Merchant, base: str, attempt: int) -> str:
    response = VoiceResponse()
    gather = Gather(
        num_digits=1,
        action=f"{base}/twilio/gather/{order.id}?attempt={attempt}",
        method="POST",
        timeout=8,
    )
    _say(gather, prompt_text(order, merchant))
    response.append(gather)
    # Gather fell through: no digit pressed within the timeout.
    if attempt < MAX_PROMPT_ATTEMPTS:
        response.redirect(f"{base}/twilio/twiml/{order.id}?attempt={attempt + 1}", method="POST")
    else:
        _say(response, "কোনো ইনপুট পাওয়া যায়নি। পরে আবার কল করা হবে। ধন্যবাদ।")
        response.hangup()
    return str(response)


def build_result_twiml(
    order: Order, merchant: Merchant, base: str, digit: str, attempt: int
) -> tuple[str, str]:
    """TwiML + outcome ("confirmed"/"cancelled"/"transfer"/"") for a pressed digit."""
    response = VoiceResponse()
    if digit == "1":
        _say(response, "ধন্যবাদ! আপনার অর্ডারটি নিশ্চিত করা হয়েছে। ভালো থাকবেন।")
        response.hangup()
        return str(response), "confirmed"
    if digit == "2":
        _say(response, "ঠিক আছে, আপনার অর্ডারটি বাতিল করা হয়েছে। ধন্যবাদ।")
        response.hangup()
        return str(response), "cancelled"
    if digit == "3" and merchant.support_phone:
        from app.services.call_service import normalize_bd_phone

        _say(response, "আপনাকে একজন প্রতিনিধির সাথে সংযোগ দেওয়া হচ্ছে, একটু লাইনে থাকুন।")
        response.dial(normalize_bd_phone(merchant.support_phone), timeout=25)
        return str(response), "transfer"
    # Unrecognized digit: re-prompt within the attempt budget, then give up.
    if attempt < MAX_PROMPT_ATTEMPTS:
        response.redirect(f"{base}/twilio/twiml/{order.id}?attempt={attempt + 1}", method="POST")
    else:
        _say(response, "দুঃখিত, বুঝতে পারিনি। পরে আবার কল করা হবে। ধন্যবাদ।")
        response.hangup()
    return str(response), ""
