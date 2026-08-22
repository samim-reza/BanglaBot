"""Static (no-AI) call: spoken summary + keypad answers, per service flow.

Used when the merchant's voice tier is "static". Instead of connecting the
media-stream agent, the TwiML endpoint speaks the flow's summary with
Twilio's built-in Bengali voice and gathers one DTMF digit. The digit map
comes from the merchant's service flow (app/flows): ecommerce is
1=confirm / 2=cancel / 3=human, courier adds 2=reschedule / 3=refuse /
4=human. No input re-prompts once, then hangs up (the status callback then
settles the order to needs_review as usual).
"""

from twilio.twiml.voice_response import Gather, VoiceResponse

from app.core.config import get_settings
from app.flows import get_flow
from app.models import Merchant, Order

MAX_PROMPT_ATTEMPTS = 2


def _say(node, text: str) -> None:
    settings = get_settings()
    node.say(text, language="bn-IN", voice=settings.twilio_say_voice)


def prompt_text(order: Order, merchant: Merchant) -> str:
    flow = get_flow(merchant.service_type)
    opening = (
        merchant.custom_greeting.strip()
        or f"আসসালামু আলাইকুম। {merchant.business_name} থেকে বলছি।"
    )
    return " ".join([opening, *flow.static_prompt_bn(order, merchant)])


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
    """TwiML + outcome ("confirmed"/"cancelled"/"rescheduled"/"transfer"/"")."""
    flow = get_flow(merchant.service_type)
    response = VoiceResponse()
    reply = flow.static_digits(merchant).get(digit)
    if reply:
        say_text, outcome = reply
        if outcome == "transfer":
            from app.services.call_service import normalize_bd_phone

            _say(response, "আপনাকে একজন প্রতিনিধির সাথে সংযোগ দেওয়া হচ্ছে, একটু লাইনে থাকুন।")
            response.dial(normalize_bd_phone(merchant.support_phone), timeout=25)
            return str(response), "transfer"
        _say(response, say_text)
        response.hangup()
        return str(response), outcome
    # Unrecognized digit: re-prompt within the attempt budget, then give up.
    if attempt < MAX_PROMPT_ATTEMPTS:
        response.redirect(f"{base}/twilio/twiml/{order.id}?attempt={attempt + 1}", method="POST")
    else:
        _say(response, "দুঃখিত, বুঝতে পারিনি। পরে আবার কল করা হবে। ধন্যবাদ।")
        response.hangup()
    return str(response), ""
