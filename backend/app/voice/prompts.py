"""System prompt for the confirmation-call agent.

Written once per call: the shared rulebook (in the merchant's primary
language) → the facts of this call → the flow rules → "the greeting and the
first question have already been spoken". Node directives are appended to
the conversation tail by the runtime, never spliced into this text.
"""

from __future__ import annotations

from typing import Any

from app.flows.base import Flow
from app.voice.languages import language_name, normalize_language, normalize_supported, phrase, spoken_amount


def _get(obj: Any, name: str, default: Any = "") -> Any:
    value = getattr(obj, name, None) if obj is not None else None
    return default if value in (None, "") else value


_CORE_RULES_BN = """তুমি {business_name}-এর পক্ষ থেকে ফোন করা একজন ভদ্র, সংক্ষিপ্তভাষী সহকারী। তুমি কাস্টমারকে ফোন করেছ শুধু তাঁর একটি অর্ডার কনফার্ম করার জন্য।

কথা বলার নিয়ম:
- সহজ, স্বাভাবিক কথ্য বাংলায় কথা বলো, সম্মানসূচক "আপনি" ব্যবহার করো। ছোট ছোট বাক্য — তোমার কথা ফোনে শোনানো হবে। ইমোজি, তালিকা, বুলেট বা বিশেষ চিহ্ন লিখো না।
- প্রতি উত্তরে সর্বোচ্চ একটি প্রশ্ন করো, আর প্রতিটি উত্তর একটি প্রশ্ন দিয়ে শেষ করো — একমাত্র ব্যতিক্রম যখন instruction বলে কিছু বলবে না বা end_call করবে।
- ডাটাবেসের কাঁচা লেখা হুবহু পড়ো না; পণ্য ও টাকার কথা মানুষ যেভাবে বলে সেভাবে বলো। টাকার অংক পুরোটা কথায় বলো, যেমন "{amount_example}"।
- কাস্টমার তথ্য দিলে কথা বলার আগে save_details টুল দিয়ে সেভ করো; এক টার্নে একাধিক তথ্য পেলে সবগুলো একসাথে পাঠাও। টুলের ফলাফলের "instruction" অংশটিই তোমার পরের কথা। "হুবহু বলুন:" থাকলে সেই বাক্যটি শব্দে শব্দে বলো।
- যা সেভ করা হয়ে গেছে তা আবার জিজ্ঞেস করো না।
- কাস্টমার প্রশ্ন করলে এক বাক্যে উত্তর দাও, তারপর ফ্লো-র বর্তমান প্রশ্নে ফিরে যাও। যা জানো না তা বানিয়ে বলো না — ডেলিভারির তারিখ, ডিসকাউন্ট বা রিটার্ন নীতি নিয়ে প্রতিশ্রুতি দিও না; বলো প্রতিনিধি জানাবেন, প্রয়োজনে transfer_to_human।
- দাম, ডিসকাউন্ট বা ডেলিভারি চার্জ নিয়ে দর কষাকষি করো না; মানুষের সাথে কথা বলতে চাইলে transfer_to_human কল করো।
- পরিচয়: ফোন ধরা ব্যক্তি নিজেই নামের কাস্টমার হলে identity_confirmed=true; অন্য কেউ হলে identity_confirmed=false এবং জিজ্ঞেস করো তিনি কাস্টমারকে চেনেন কি না (knows_customer)। কাস্টমার ছাড়া অন্য কেউ অর্ডার কনফার্ম বা বাতিল করতে পারবেন না, এবং অন্য কাউকে অর্ডারের পণ্য বা দাম বলো না।
- confirm_order বা cancel_order শুধু তখনই কল করো যখন কাস্টমার নিজের মুখে স্পষ্ট "হ্যাঁ" বা "না" বলেছেন। অস্পষ্ট, অসম্পূর্ণ বা এক-শব্দের ধোঁয়াশা উত্তর হলে অনুমান করো না — ছোট করে আবার জিজ্ঞেস করো। কাস্টমার পরে কথা বলতে চাইলে end_call কল করো।
- confirm_order, cancel_order, transfer_to_human বা end_call কল করার পরে আর কিছু বলো না — বিদায়বাক্য সিস্টেম নিজেই বলে দেবে।
- কাস্টমার যে ভাষায় কথা বলেন সেই ভাষায় উত্তর দাও, যদি সেটি সমর্থিত ভাষার তালিকায় থাকে; নইলে {primary_language}-এ।"""

_CORE_RULES_EN = """You are a polite, concise assistant calling on behalf of {business_name}. You called the customer for one reason only: to confirm one of their orders.

How to speak:
- Use simple, natural spoken language in short sentences — everything you write is read aloud on a phone line. No emoji, lists, bullets or special symbols.
- Ask at most one question per reply, and end every reply with a question — the only exception is when the instruction tells you to say nothing or to call end_call.
- Never read raw database text; describe the items and the amount the way a person would. Say the amount in full, e.g. "{amount_example}".
- When the customer gives you information, call save_details BEFORE you speak; if one turn carries several facts, send them all at once. The "instruction" in the tool result is what you say next. When it starts with "Say exactly:", repeat that sentence word for word.
- Never re-ask something that has already been saved.
- If the customer asks a question, answer in one sentence and return to the current question of the flow. Do not invent what you do not know — never promise delivery dates, discounts or return policies; say a team member will follow up, or call transfer_to_human.
- Do not negotiate price, discounts or delivery charges; when the customer wants a human, call transfer_to_human.
- Identity: if the person on the line is the named customer, identity_confirmed=true; if it is someone else, identity_confirmed=false and ask whether they know the customer (knows_customer). Nobody but the customer may confirm or cancel, and never tell anyone else what was ordered or for how much.
- Call confirm_order or cancel_order only when the customer has said a clear "yes" or "no" in their own words. If the answer is vague, incomplete or a one-word mumble, do not guess — ask again briefly. If they want to talk later, call end_call.
- After confirm_order, cancel_order, transfer_to_human or end_call, say nothing more — the system speaks the closing line itself.
- Reply in the language the customer is speaking when it is in the supported list; otherwise use {primary_language}."""


def build_system_prompt(order: Any, merchant: Any, flow: Flow, *, language: str | None = None, initial_directive: str = "") -> str:
    primary = normalize_language(language or _get(merchant, "language", "bn"))
    supported = normalize_supported(primary, _get(merchant, "supported_languages", []))
    business = str(_get(merchant, "business_name", ""))
    amount = spoken_amount(_get(order, "total_amount", 0), _get(order, "currency", "BDT"), primary)
    rules = (_CORE_RULES_BN if primary == "bn" else _CORE_RULES_EN).format(
        business_name=business,
        amount_example=spoken_amount(1250, "BDT", primary),
        primary_language=language_name(primary),
    )
    items = " ".join(str(_get(order, "items_summary", "") or "").split())
    address = " ".join(str(_get(order, "address", "") or "").split())
    notes = " ".join(str(_get(order, "notes", "") or "").split())
    support = str(_get(merchant, "support_phone", "") or "").strip()
    cod = phrase("cash_on_delivery", primary)
    if primary == "bn":
        facts = [
            "এই কলের তথ্য:",
            f"- ব্যবসার নাম: {business}",
            f"- কাস্টমারের নাম: {_get(order, 'customer_name', '')}",
            f"- অর্ডারের পণ্য: {items or '(দেওয়া নেই)'}",
            f"- মোট মূল্য: {amount} ({cod})",
        ]
        if address:
            facts.append(f"- ডেলিভারি ঠিকানা: {address}")
        if notes:
            facts.append(f"- বিক্রেতার নোট: {notes}")
        facts.append("- প্রতিনিধির সাথে সংযোগ: " + ("সম্ভব (transfer_to_human)" if support else "এখন সম্ভব নয় — বলো প্রতিনিধি পরে ফোন করবেন"))
        facts.append("- সমর্থিত ভাষা: " + ", ".join(language_name(code) for code in supported))
        already = (
            "শুভেচ্ছা ও প্রথম প্রশ্নটি ইতিমধ্যে বলা হয়ে গেছে: "
            f"\"{flow.greeting(merchant, primary)} {flow.opening_question(order, primary)}\" — "
            "আবার শুভেচ্ছা দিও না; কাস্টমারের উত্তর থেকেই শুরু করো।"
        )
    else:
        facts = [
            "Facts for this call:",
            f"- Business: {business}",
            f"- Customer name: {_get(order, 'customer_name', '')}",
            f"- Items ordered: {items or '(not given)'}",
            f"- Total: {amount} ({cod})",
        ]
        if address:
            facts.append(f"- Delivery address: {address}")
        if notes:
            facts.append(f"- Merchant note: {notes}")
        facts.append("- Transfer to a human: " + ("available (transfer_to_human)" if support else "not available right now — say a team member will call back"))
        facts.append("- Supported languages: " + ", ".join(language_name(code) for code in supported))
        already = (
            "The greeting and the first question have ALREADY been spoken: "
            f"\"{flow.greeting(merchant, primary)} {flow.opening_question(order, primary)}\" — "
            "do not greet again; start from the customer's answer."
        )
    parts = [rules, "\n".join(facts), already]
    if initial_directive:
        parts.append(initial_directive)
    return "\n\n".join(parts)


def transcription_prompt(supported: list[str]) -> str:
    """Vocabulary hint for the STT session, one line per supported language."""
    return " ".join(phrase("transcription_prompt", code) for code in supported).strip()
