"""Courier delivery-confirmation flow: identity → parcel/address → time → decision.

Built for RTO-reduction calls: the courier calls the recipient before the
delivery attempt to learn whether the parcel will be received (confirmed),
should go out another day (rescheduled — the order stays callable), or is
refused (cancelled → return to sender).
"""

from __future__ import annotations

from typing import Any

from app.flows.base import (
    NODE_DECISION,
    NODE_IDENTITY,
    NODE_KNOWS_PERSON,
    NODE_SCHEDULE,
    NODE_WRAP_UP,
    STAGE_ADDRESS,
    STAGE_DECISION,
    STAGE_IDENTITY,
    STAGE_KNOWS_PERSON,
    STAGE_RELAY,
    STAGE_SCHEDULE,
    STAGE_WRONG_NUMBER,
    Flow,
    Terminal,
    taka_bn,
)
from app.models import Merchant, Order, OrderStatus

# Courier groups parcel read-back + address check into one node (like
# Sloancode's FULFILLMENT bundling several checklist stages).
NODE_PARCEL = "parcel"


def _parcel_summary_bn(order: Order) -> str:
    parts = [f"একটি পার্সেল ({order.order_ref or order.id[:8]})"]
    if order.items_summary:
        parts.append(order.items_summary)
    amount = float(order.total_amount or 0)
    if amount > 0:
        parts.append(f"ক্যাশ অন ডেলিভারি {taka_bn(order.total_amount)} টাকা")
    return ", ".join(parts)


class CourierFlow(Flow):
    key = "courier"
    name_bn = "কুরিয়ার"
    description_bn = "ডেলিভারির আগে প্রাপককে কল — পার্সেল নেবেন কি না, কখন নেবেন, ঠিকানা ঠিক আছে কি না।"
    icon = "📦"
    order_noun_bn = "পার্সেল"
    call_label_bn = "ডেলিভারি কল"
    settings_spec = {
        "verify_address": (
            True,
            "ডেলিভারি ঠিকানা যাচাই",
            "এজেন্ট ঠিকানাটি পড়ে শুনিয়ে ঠিক আছে কি না জিজ্ঞেস করবে।",
        ),
        "ask_delivery_time": (
            True,
            "সুবিধাজনক সময় জানা",
            "এজেন্ট জিজ্ঞেস করবে আজ দিনের কোন সময়ে ডেলিভারি নিতে সুবিধা হবে।",
        ),
    }
    node_order = (NODE_IDENTITY, NODE_KNOWS_PERSON, NODE_PARCEL, NODE_SCHEDULE, NODE_DECISION, NODE_WRAP_UP)

    def slot_properties(self) -> dict[str, Any]:
        props = super().slot_properties()
        props["delivery_time"] = {
            "type": "string",
            "description": "আজ কোন সময়ে ডেলিভারি নিতে পারবেন — কাস্টমারের কথায় (যেমন: বিকেল পাঁচটার পরে)।",
        }
        return props

    def next_missing_stage(
        self, slots: dict[str, Any], settings: dict[str, bool], order: Order
    ) -> str:
        gate = self.identity_gate_stage(slots)
        if gate:
            return gate
        if settings.get("verify_address") and (order.address or "").strip():
            if slots.get("address_correct") is None:
                return STAGE_ADDRESS
            if slots.get("address_correct") is False and not slots.get("new_address"):
                return STAGE_ADDRESS
        if settings.get("ask_delivery_time") and not slots.get("delivery_time"):
            return STAGE_SCHEDULE
        return STAGE_DECISION

    def node_for_stage(self, stage: str) -> str:
        return {
            STAGE_IDENTITY: NODE_IDENTITY,
            STAGE_KNOWS_PERSON: NODE_KNOWS_PERSON,
            STAGE_ADDRESS: NODE_PARCEL,
            STAGE_SCHEDULE: NODE_SCHEDULE,
            STAGE_DECISION: NODE_DECISION,
            STAGE_RELAY: NODE_WRAP_UP,
            STAGE_WRONG_NUMBER: NODE_WRAP_UP,
        }[stage]

    def node_task_bn(self, node: str, order: Order, merchant: Merchant) -> str:
        tasks = {
            NODE_IDENTITY: (
                "বর্তমান ধাপ: পরিচয় নিশ্চিত করা\n"
                f"- তিনি {order.customer_name} কি না — হুবহু opening question।\n"
                "- হ্যাঁ হলে save_details-এ identity_confirmed=true পাঠাবে।\n"
                "- না হলে identity_confirmed=false পাঠাবে (অন্য কেউ পার্সেল কনফার্ম করতে পারবে না)।"
            ),
            NODE_KNOWS_PERSON: (
                "বর্তমান ধাপ: প্রাপককে চেনেন কি না\n"
                f"- হুবহু জিজ্ঞেস করো তিনি {order.customer_name}-কে চেনেন কি না।\n"
                "- হ্যাঁ হলে knows_customer=true; না হলে knows_customer=false।"
            ),
            NODE_PARCEL: (
                "বর্তমান ধাপ: পার্সেল ও ঠিকানা\n"
                f"- জানাও যে তার নামে {_parcel_summary_bn(order)} এসেছে।\n"
                f"- ঠিকানাটি পড়ে শোনাও: \"{(order.address or '').strip()}\" — ঠিক আছে কি না জিজ্ঞেস করো।\n"
                "- ঠিক থাকলে address_correct=true; ভুল হলে address_correct=false এবং নতুন ঠিকানা new_address-এ হুবহু লিখবে।"
            ),
            NODE_SCHEDULE: (
                "বর্তমান ধাপ: ডেলিভারির সময়\n"
                "- জিজ্ঞেস করো আজ দিনের কোন সময়ে ডেলিভারি নিতে সুবিধা হবে; উত্তরটি delivery_time-এ সেভ করো।\n"
                "- কাস্টমার আজ নয়, অন্য দিন নিতে চাইলে reschedule_delivery টুল কল করবে (when-এ সময়টা লিখে)।\n"
                "- পার্সেল নিতে না চাইলে একবার কারণ জিজ্ঞেস করে refuse_parcel কল করবে।"
            ),
            NODE_DECISION: (
                "বর্তমান ধাপ: ডেলিভারি নিশ্চিত করা\n"
                "- সংক্ষেপে মিলিয়ে নাও (পার্সেল, সিওডি টাকা, সময়) এবং জিজ্ঞেস করো তিনি পার্সেলটি গ্রহণ করবেন কি না।\n"
                "- গ্রহণ করলে confirm_delivery কল করবে; সিওডি টাকা রেডি রাখতে মনে করিয়ে দেবে।\n"
                "- অন্য দিন নিতে চাইলে reschedule_delivery (when-এ সময়); নিতে না চাইলে একবার কারণ জিজ্ঞেস করে refuse_parcel।"
            ),
            NODE_WRAP_UP: (
                "বর্তমান ধাপ: কল শেষ করা\n"
                "- কিছু বলো না। এখনই end_call টুল কল করো — বিদায়বাক্য টুল নিজে বলে দেবে।"
            ),
        }
        return tasks[node]

    def spoken_instruction_bn(
        self,
        stage: str,
        slots: dict[str, Any],
        settings: dict[str, bool],
        order: Order,
        merchant: Merchant,
    ) -> str:
        scripted = self.spoken_identity_instruction_bn(stage, order)
        if scripted:
            return scripted
        if stage == STAGE_ADDRESS:
            if slots.get("address_correct") is False:
                return "জিজ্ঞেস করো: তাহলে সঠিক ঠিকানাটি বলুন — এবং উত্তরটি new_address-এ সেভ করো।"
            return (
                f"জানাও যে তার নামে {_parcel_summary_bn(order)} এসেছে, তারপর ঠিকানাটি পড়ে শোনাও "
                f"(\"{(order.address or '').strip()}\") এবং জিজ্ঞেস করো ঠিক আছে কি না।"
            )
        if stage == STAGE_SCHEDULE:
            question = "জিজ্ঞেস করো: আজ দিনের কোন সময়ে ডেলিভারিটা নিলে আপনার সুবিধা হয়?"
            # Address verification off → this is the first content step, so the
            # parcel announcement happens here.
            if not settings.get("verify_address") or not (order.address or "").strip():
                return f"জানাও যে তার নামে {_parcel_summary_bn(order)} এসেছে, তারপর {question}"
            return question
        # decision — always restate the short summary in the final question.
        time_part = ""
        if slots.get("delivery_time"):
            time_part = f" {slots['delivery_time']}-এ ডেলিভারি হবে বলে,"
        amount = float(order.total_amount or 0)
        cod_part = (
            f" সিওডি {taka_bn(order.total_amount)} টাকা রেডি রাখার কথা মনে করিয়ে দিয়ে,"
            if amount > 0
            else ""
        )
        return (
            f"সংক্ষেপে মিলিয়ে নাও — তার নামে {_parcel_summary_bn(order)} এসেছে,{time_part}{cod_part} "
            "জিজ্ঞেস করো তিনি পার্সেলটি গ্রহণ করবেন কি না। "
            "গ্রহণ করলে confirm_delivery, অন্য দিন চাইলে reschedule_delivery, নিতে না চাইলে refuse_parcel।"
        )

    def system_facts_bn(
        self, order: Order, merchant: Merchant, settings: dict[str, bool]
    ) -> str:
        amount = float(order.total_amount or 0)
        cod_line = (
            f"- সিওডি (ক্যাশ অন ডেলিভারি): {taka_bn(order.total_amount)} টাকা"
            if amount > 0
            else "- সিওডি: নেই (আগে পরিশোধিত)"
        )
        return f"""
তুমি কুরিয়ার সার্ভিস "{merchant.business_name}"-এর পক্ষ থেকে ফোন করা একজন ভদ্র মহিলা এজেন্ট।
তোমার কাজ: প্রাপক পার্সেলটি গ্রহণ করবেন কি না, কখন নেবেন এবং ঠিকানা ঠিক আছে কি না তা জানা।

পার্সেলের তথ্য:
- প্রাপকের নাম: {order.customer_name}
- ট্র্যাকিং নম্বর: {order.order_ref or order.id[:8]}
- পার্সেলের বিবরণ: {order.items_summary or "N/A"}
{cod_line}
- ডেলিভারি ঠিকানা: {order.address or "N/A"}
""".strip()

    def terminals(self) -> list[Terminal]:
        return [
            Terminal(
                name="confirm_delivery",
                description_bn="প্রাপক পার্সেলটি গ্রহণ করবেন বললে এটি কল করো।",
                status=OrderStatus.confirmed,
                outcome="confirmed",
                properties={},
            ),
            Terminal(
                name="reschedule_delivery",
                description_bn="প্রাপক অন্য দিন/সময়ে ডেলিভারি নিতে চাইলে এটি কল করো।",
                status=OrderStatus.rescheduled,
                outcome="rescheduled",
                properties={
                    "when": {
                        "type": "string",
                        "description": "কবে/কখন ডেলিভারি চান — কাস্টমারের কথায় (বাংলায়)।",
                    }
                },
                note_bn="রিশিডিউল: {when}",
            ),
            Terminal(
                name="refuse_parcel",
                description_bn="প্রাপক পার্সেলটি নিতে অস্বীকার করলে এটি কল করো।",
                status=OrderStatus.cancelled,
                outcome="cancelled",
                properties={
                    "reason": {"type": "string", "description": "না নেওয়ার কারণ (বাংলায়)"}
                },
                note_bn="প্রত্যাখ্যানের কারণ: {reason}",
            ),
        ]

    def static_prompt_bn(self, order: Order, merchant: Merchant) -> list[str]:
        amount = float(order.total_amount or 0)
        cod = f" সিওডি {taka_bn(order.total_amount)} টাকা।" if amount > 0 else ""
        lines = [
            f"{order.customer_name}, আপনার নামে {_parcel_summary_bn(order)} এসেছে।{cod}",
            "পার্সেলটি আজ নিতে ১ চাপুন। অন্য দিন নিতে ২ চাপুন। নিতে না চাইলে ৩ চাপুন।",
        ]
        if merchant.support_phone:
            lines.append("প্রতিনিধির সাথে কথা বলতে ৪ চাপুন।")
        return lines

    def static_digits(self, merchant: Merchant) -> dict[str, tuple[str, str]]:
        digits = {
            "1": (
                "ধন্যবাদ! পার্সেলটি আজ ডেলিভারি করা হবে। সিওডি টাকা রেডি রাখবেন। ভালো থাকবেন।",
                "confirmed",
            ),
            "2": ("ঠিক আছে, ডেলিভারিটি পরে আবার শিডিউল করা হবে। ধন্যবাদ।", "rescheduled"),
            "3": ("ঠিক আছে, পার্সেলটি ফেরত পাঠানো হবে। ধন্যবাদ।", "cancelled"),
        }
        if merchant.support_phone:
            digits["4"] = ("", "transfer")
        return digits

    def preview_steps_bn(self, settings: dict[str, bool]) -> list[str]:
        steps = [
            "সালাম, তারপর আমি কি নাম-এর সাথে কথা বলছি?",
            "না হলে নাম-কে চিনেন? — চেনেন তো রিসিভ করতে বলা; না চিনলে দুঃখ করে কল শেষ",
        ]
        if settings.get("verify_address"):
            steps.append("পার্সেলের খবর দিয়ে ঠিকানা যাচাই")
        else:
            steps.append("পার্সেলের খবর জানানো")
        if settings.get("ask_delivery_time"):
            steps.append("সুবিধাজনক ডেলিভারির সময় জানা")
        steps.append("ডেলিভারি নিশ্চিত / রিশিডিউল / ফেরত জানা")
        steps.append("ধন্যবাদ জানিয়ে কল শেষ")
        return steps
