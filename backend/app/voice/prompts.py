"""System prompt assembly for the flow-driven Bengali voice agent.

Layout follows the SloancodeAI discipline: the shared rulebook leads (one
cacheable head for every tenant), the per-call service facts follow, and the
prompt is never rewritten mid-call — step changes arrive as tail-appended
"ধাপ পরিবর্তন" system messages from the flow runtime.
"""

from app.flows import CORE_RULES_BN, FlowRuntime
from app.models import Merchant, Order


def opening_greeting(merchant: Merchant) -> str:
    """First sentence the selected TTS voice speaks when the media stream connects.

    Kept short so the caller hears the merchant's chosen voice quickly. The
    LLM is told this line already went out and must not greet again.
    """
    if merchant.custom_greeting.strip():
        return merchant.custom_greeting.strip()
    return f"আসসালামু আলাইকুম, আমি {merchant.business_name}-এর পক্ষ থেকে বলছি।"


def build_system_prompt(order: Order, merchant: Merchant, runtime: FlowRuntime) -> str:
    greeting = opening_greeting(merchant)
    opening_question = runtime.opening_question_bn()
    return f"""
{CORE_RULES_BN}

{runtime.flow.system_facts_bn(order, merchant, runtime.settings)}

ফ্লো-র নিয়ম:
- কথোপকথন ধাপে ধাপে এগোয়। "ধাপ পরিবর্তন" চিহ্নিত বার্তাগুলোই বর্তমান ধাপের নির্দেশ — সর্বশেষটি মানবে।
- কাস্টমারের দেওয়া প্রতিটি তথ্য সাথে সাথে save_details টুলে সেভ করবে; টুলের ফলাফলের "instruction" অনুযায়ী পরের কথা বলবে।
- কলের একদম শুরুতে কাস্টমার ইতিমধ্যে এই গ্রিটিং শুনে ফেলেছেন: "{greeting}" এবং তুমি প্রথম প্রশ্নটিও করে ফেলেছ: "{opening_question}" — তাই আবার সালাম, পরিচয় বা এই প্রশ্ন দেবে না; কাস্টমারের উত্তর থেকে শুরু করবে (উত্তর অস্পষ্ট হলে সংক্ষেপে আবার জিজ্ঞেস করতে পারো)।

এখন কল শুরু হয়েছে — গ্রিটিং ও প্রথম প্রশ্ন বলা হয়ে গেছে; কাস্টমারের উত্তরের অপেক্ষায় আছ। উত্তর পেলে save_details দিয়ে সেভ করে টুলের instruction অনুযায়ী এগোবে।
""".strip()
