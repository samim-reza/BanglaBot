"""Ecommerce order-confirmation flow: identity → (address) → confirm/cancel."""

from __future__ import annotations

from typing import Any

from app.flows.base import (
    NODE_ADDRESS,
    NODE_DECISION,
    NODE_IDENTITY,
    NODE_KNOWS_PERSON,
    NODE_WRAP_UP,
    STAGE_ADDRESS,
    STAGE_DECISION,
    STAGE_IDENTITY,
    STAGE_KNOWS_PERSON,
    STAGE_RELAY,
    STAGE_WRONG_NUMBER,
    Flow,
    Terminal,
    taka_bn,
)
from app.models import Merchant, Order, OrderStatus


class EcommerceFlow(Flow):
    key = "ecommerce"
    name_bn = "ই-কমার্স"
    description_bn = "অনলাইন শপের অর্ডার কনফার্মেশন কল — কাস্টমার অর্ডারটি নিশ্চিত করছেন কি না।"
    icon = "🛍️"
    order_noun_bn = "অর্ডার"
    call_label_bn = "কনফার্মেশন কল"
    settings_spec = {
        "verify_address": (
            False,
            "ডেলিভারি ঠিকানা যাচাই",
            "কনফার্মের আগে এজেন্ট ঠিকানাটি পড়ে শুনিয়ে ঠিক আছে কি না জিজ্ঞেস করবে।",
        ),
    }
    node_order = (NODE_IDENTITY, NODE_KNOWS_PERSON, NODE_ADDRESS, NODE_DECISION, NODE_WRAP_UP)

    def next_missing_stage(
        self, slots: dict[str, Any], settings: dict[str, bool], order: Order
    ) -> str:
        gate = self.identity_gate_stage(slots)
        if gate:
            return gate
        if settings.get("verify_address") and (order.address or "").strip():
            # Answered = a yes, or a no that came with the corrected address.
            if slots.get("address_correct") is None:
                return STAGE_ADDRESS
            if slots.get("address_correct") is False and not slots.get("new_address"):
                return STAGE_ADDRESS
        return STAGE_DECISION

    def node_for_stage(self, stage: str) -> str:
        return {
            STAGE_IDENTITY: NODE_IDENTITY,
            STAGE_KNOWS_PERSON: NODE_KNOWS_PERSON,
            STAGE_ADDRESS: NODE_ADDRESS,
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
                "- না হলে identity_confirmed=false পাঠাবে (অন্য কেউ অর্ডার কনফার্ম করতে পারবে না)।"
            ),
            NODE_KNOWS_PERSON: (
                "বর্তমান ধাপ: কাস্টমারকে চেনেন কি না\n"
                f"- হুবহু জিজ্ঞেস করো তিনি {order.customer_name}-কে চেনেন কি না।\n"
                "- হ্যাঁ হলে knows_customer=true; না হলে knows_customer=false।"
            ),
            NODE_ADDRESS: (
                "বর্তমান ধাপ: ঠিকানা যাচাই\n"
                f"- ডেলিভারি ঠিকানাটি পড়ে শোনাও: \"{(order.address or '').strip()}\" — ঠিক আছে কি না জিজ্ঞেস করো।\n"
                "- ঠিক থাকলে address_correct=true; ভুল হলে address_correct=false এবং নতুন ঠিকানা new_address-এ হুবহু লিখবে।"
            ),
            NODE_DECISION: (
                "বর্তমান ধাপ: অর্ডার কনফার্মেশন\n"
                f"- হুবহু বলো: আপনি {self.order_details_bn(order)} অর্ডার করেছেন, আপনি কি কনফার্ম করতে চান?\n"
                "- হ্যাঁ হলে সাথে সাথে confirm_order টুল কল করবে।\n"
                "- না হলে সাথে সাথে cancel_order টুল কল করবে — কারণ জিজ্ঞেস করবে না, বললে reason-এ লিখবে।"
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
                f"ঠিকানাটি পড়ে শোনাও (\"{(order.address or '').strip()}\") এবং জিজ্ঞেস করো ঠিক আছে কি না।"
            )
        # decision — exact confirm line; LLM must not paraphrase.
        return (
            f"হুবহু বলো: আপনি {self.order_details_bn(order)} অর্ডার করেছেন, "
            "আপনি কি কনফার্ম করতে চান? "
            "হ্যাঁ হলে সাথে সাথে confirm_order, না হলে সাথে সাথে cancel_order।"
        )

    def system_facts_bn(
        self, order: Order, merchant: Merchant, settings: dict[str, bool]
    ) -> str:
        return f"""
তুমি "{merchant.business_name}"-এর পক্ষ থেকে ফোন করা একজন ভদ্র মহিলা কাস্টমার-কেয়ার এজেন্ট।
তোমার কাজ: নিচের অর্ডারটি কাস্টমার নিশ্চিত (confirm) করছেন কি না তা জানা।

অর্ডারের তথ্য:
- কাস্টমারের নাম: {order.customer_name}
- অর্ডার নম্বর: {order.order_ref or order.id[:8]}
- পণ্য: {order.items_summary or "N/A"}
- মোট মূল্য: {taka_bn(order.total_amount)} টাকা (ক্যাশ অন ডেলিভারি)
- ডেলিভারি ঠিকানা: {order.address or "N/A"}
""".strip()

    def terminals(self) -> list[Terminal]:
        return [
            Terminal(
                name="confirm_order",
                description_bn="কাস্টমার অর্ডারটি নিশ্চিত করলে এটি কল করো।",
                status=OrderStatus.confirmed,
                outcome="confirmed",
                properties={},
            ),
            Terminal(
                name="cancel_order",
                description_bn="কাস্টমার অর্ডারটি বাতিল করলে এটি কল করো।",
                status=OrderStatus.cancelled,
                outcome="cancelled",
                properties={
                    "reason": {"type": "string", "description": "বাতিলের কারণ (বাংলায়)"}
                },
                note_bn="বাতিলের কারণ: {reason}",
            ),
        ]

    def static_prompt_bn(self, order: Order, merchant: Merchant) -> list[str]:
        lines = [
            f"{order.customer_name}, আপনার অর্ডার"
            + (f" {order.items_summary}," if order.items_summary else "")
            + f" মোট {taka_bn(order.total_amount)} টাকা, ক্যাশ অন ডেলিভারি।",
            "অর্ডারটি নিশ্চিত করতে ১ চাপুন। বাতিল করতে ২ চাপুন।",
        ]
        if merchant.support_phone:
            lines.append("প্রতিনিধির সাথে কথা বলতে ৩ চাপুন।")
        return lines

    def static_digits(self, merchant: Merchant) -> dict[str, tuple[str, str]]:
        digits = {
            "1": ("ধন্যবাদ! আপনার অর্ডারটি নিশ্চিত করা হয়েছে। ভালো থাকবেন।", "confirmed"),
            "2": ("ঠিক আছে, আপনার অর্ডারটি বাতিল করা হয়েছে। ধন্যবাদ।", "cancelled"),
        }
        if merchant.support_phone:
            digits["3"] = ("", "transfer")
        return digits

    def preview_steps_bn(self, settings: dict[str, bool]) -> list[str]:
        steps = [
            "সালাম, তারপর আমি কি নাম-এর সাথে কথা বলছি?",
            "হ্যাঁ হলে অর্ডারের বিবরণ বলে কনফার্ম/বাতিল জানা",
            "না হলে নাম-কে চিনেন? — চেনেন তো কনফার্ম করতে বলা; না চিনলে দুঃখ করে কল শেষ",
        ]
        if settings.get("verify_address"):
            steps.insert(1, "ডেলিভারি ঠিকানা যাচাই")
        steps.append("ধন্যবাদ জানিয়ে কল শেষ")
        return steps
