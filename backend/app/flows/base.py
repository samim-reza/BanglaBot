"""Node-based conversation flow engine (pattern ported from SloancodeAI).

The central idea: the current node is DERIVED from the collected answers on
every tool call — it is never stored as an authoritative pointer. An ordered
slot cascade (`next_missing_stage`) returns the next thing the caller still
owes; a coarser mapper (`node_for_stage`) groups stages into instruction
bundles ("nodes"). Skipping a question the caller already answered — whether
volunteered early or pre-filled from the order — is simply the absence of a
return in the cascade. Backward jumps and corrections need no special
handling because there is no pointer that can go stale.

Prompt discipline (also from SloancodeAI): the system prompt is written once
per call and never rewritten; when the node changes, a short Bengali
"ধাপ পরিবর্তন" directive is appended to the TAIL of the conversation, and the
slot-saving tool's result carries the backend-owned wording of the next
question so the model never invents its own checklist.

Each service vertical (ecommerce, courier) subclasses `Flow`. Keep this
package free of pipecat imports — it is pure conversation logic, imported by
schemas and API routes too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — only for type hints
    from app.models import Merchant, Order, OrderStatus

# Stage keys shared across flows (a flow may use a subset).
STAGE_IDENTITY = "identity"
STAGE_KNOWS_PERSON = "knows_person"
STAGE_RELAY = "relay"
STAGE_ADDRESS = "address"
STAGE_SCHEDULE = "schedule"
STAGE_DECISION = "decision"
STAGE_WRONG_NUMBER = "wrong_number"

# Node keys (instruction bundles). Several stages may map to one node.
NODE_IDENTITY = "identity"
NODE_KNOWS_PERSON = "knows_person"
NODE_ADDRESS = "address"
NODE_SCHEDULE = "schedule"
NODE_DECISION = "decision"
NODE_WRAP_UP = "wrap_up"

# The one Bengali rulebook shared by every service — every rule appears exactly
# once, and it leads the system prompt so all tenants share a cacheable head.
CORE_RULES_BN = """
কথা বলার মূল নিয়ম (সব সময় মানবে):
- সবসময় সহজ, প্রমিত বাংলায় কথা বলবে। ছোট ছোট বাক্য — উত্তরগুলো ফোনে শোনানো হবে। কাস্টমার ইংরেজিতে বললেও বাংলায় উত্তর দেবে।
- সংখ্যা বাংলায় উচ্চারণ করবে (যেমন: এক হাজার দুইশ টাকা)। ইমোজি, তালিকা বা বিশেষ চিহ্ন ব্যবহার করবে না।
- প্রতি বার্তায় সর্বোচ্চ একটি প্রশ্ন করবে। টুলের ফলাফলে "instruction" থাকলে সেটাই তোমার পরবর্তী কথা/প্রশ্ন — নিজের মতো নতুন প্রশ্ন বানাবে না। "হুবহু বলো:" থাকলে সেই বাক্যটিই বলবে, শব্দ বদলাবে না।
- কোনো বার্তা প্রশ্ন ছাড়া শেষ করবে না — প্রতিটি বার্তার শেষে পরের প্রয়োজনীয় প্রশ্নটি থাকবে, যাতে কাস্টমার বুঝতে পারেন এখন তার বলার পালা। একমাত্র ব্যতিক্রম: instruction যখন বলে কিছু বলো না / end_call করো।
- এক টার্নে সব ধরে ফেলবে: কাস্টমার একসাথে একাধিক তথ্য দিলে (যেমন পরিচয় + চেনেন কি না) সবগুলো একবারে save_details টুলে পাঠাবে — কথা বলার আগে।
- সেভ করা তথ্য আবার জিজ্ঞেস করবে না। কাস্টমার আগে থেকেই কিছু বলে দিলে save_details দিয়ে সেভ করবে, তারপর শুধু যা বাকি সেটাই জিজ্ঞেস করবে।
- কাস্টমার প্রশ্ন করলে আগে ছোট করে উত্তর দেবে, তারপর ফ্লো-র বর্তমান প্রশ্নে ফিরে আসবে।
- দাম, ডিসকাউন্ট বা ডেলিভারি চার্জ নিয়ে দর কষাকষি করবে না — এসব প্রশ্নে transfer_to_human ব্যবহার করবে।
- কাস্টমার মানুষ/প্রতিনিধির সাথে কথা বলতে চাইলে, বা এমন কিছু জিজ্ঞেস করলে যার উত্তর তোমার জানা নেই — transfer_to_human কল করবে।
- পরিচয়: তিনি নিজেই নামের ব্যক্তি হলে identity_confirmed=true; অন্য কেউ হলে identity_confirmed=false। অন্য কেউ অর্ডার কনফার্ম করতে পারবে না।
- identity_confirmed=false হলে instruction অনুযায়ী জিজ্ঞেস করবে তিনি সেই ব্যক্তিকে চেনেন কি না (knows_customer)। না চিনলে / ভুল নম্বর হলে knows_customer=false (বা wrong_person=true)।
- চূড়ান্ত ফলাফলের টুল (কনফার্ম/বাতিল/রিশিডিউল) কল করার পরে কিছু না বলে end_call টুল কল করবে — বিদায়বাক্য end_call নিজে বলে দেবে।
""".strip()


@dataclass(frozen=True)
class Terminal:
    """One call-ending outcome tool: schema + what it writes to the DB."""

    name: str
    description_bn: str
    status: "OrderStatus"
    outcome: str
    # JSON-schema properties for the tool's arguments (may be empty).
    properties: dict[str, Any]
    # Bengali note template; {arg} placeholders filled from tool arguments.
    note_bn: str = ""


class Flow:
    """One service vertical's conversation flow. Subclasses fill the class vars."""

    key: str = ""
    name_bn: str = ""
    description_bn: str = ""
    icon: str = ""
    # What the "thing being called about" is named in UI and speech.
    order_noun_bn: str = "অর্ডার"
    call_label_bn: str = "কনফার্মেশন কল"
    # Per-merchant toggles: key -> (default, label_bn, hint_bn).
    settings_spec: dict[str, tuple[bool, str, str]] = {}
    node_order: tuple[str, ...] = ()

    # ---- settings -------------------------------------------------------

    def merged_settings(self, merchant: "Merchant") -> dict[str, bool]:
        """Merchant's toggles over the service defaults; unknown keys ignored."""
        stored = merchant.flow_settings if isinstance(merchant.flow_settings, dict) else {}
        return {
            key: bool(stored.get(key, default))
            for key, (default, _label, _hint) in self.settings_spec.items()
        }

    # ---- slots ----------------------------------------------------------

    def slot_properties(self) -> dict[str, Any]:
        """JSON-schema properties of the save_details tool. Override to extend."""
        return {
            "identity_confirmed": {
                "type": "boolean",
                "description": (
                    "ফোন ধরা ব্যক্তি নিজেই অর্ডার/পার্সেলের নামের কাস্টমার হলে true; "
                    "অন্য কেউ (পরিবার/বন্ধু) হলে false।"
                ),
            },
            "knows_customer": {
                "type": "boolean",
                "description": (
                    "identity_confirmed=false হলে: তিনি নামের ব্যক্তিকে চেনেন কি না। "
                    "চেনেন true, চেনেন না / ভুল নম্বর false।"
                ),
            },
            "wrong_person": {
                "type": "boolean",
                "description": "ভুল নম্বর — ইনি কাস্টমার নন এবং কাস্টমারকেও চেনেন না।",
            },
            "address_correct": {
                "type": "boolean",
                "description": "ঠিকানা সঠিক কি না — কাস্টমারের উত্তর অনুযায়ী।",
            },
            "new_address": {
                "type": "string",
                "description": "কাস্টমার নতুন বা সংশোধিত ঠিকানা বললে হুবহু বাংলায় লিখবে।",
            },
            "note": {
                "type": "string",
                "description": "গুরুত্বপূর্ণ অতিরিক্ত তথ্য (বাংলায়, ছোট করে)।",
            },
        }

    def initial_slots(
        self, order: "Order", merchant: "Merchant", settings: dict[str, bool]
    ) -> dict[str, Any]:
        """Pre-filled answers — anything already known is never asked."""
        return {}

    # ---- scripted identity gate (shared by every service) ----------------

    def order_details_bn(self, order: "Order") -> str:
        """Short spoken summary of the thing being confirmed."""
        parts = []
        if (order.items_summary or "").strip():
            parts.append(order.items_summary.strip())
        parts.append(f"মোট {taka_bn(order.total_amount)} টাকা ক্যাশ অন ডেলিভারি")
        return ", ".join(parts)

    def identity_gate_stage(self, slots: dict[str, Any]) -> str | None:
        """Return the next identity-gate stage, or None if the named person is on the line.

        Named person → continue the service flow.
        Someone else → ask if they know the named person.
        Know them → leave a relay message and hang up (they cannot confirm).
        Don't know them → apologize and reject as a wrong number.
        """
        knows = slots.get("knows_customer")
        if slots.get("wrong_person") is True and knows is not True:
            return STAGE_WRONG_NUMBER
        if slots.get("identity_confirmed") is True:
            return None
        if slots.get("identity_confirmed") is False:
            if knows is True:
                return STAGE_RELAY
            if knows is False:
                return STAGE_WRONG_NUMBER
            return STAGE_KNOWS_PERSON
        return STAGE_IDENTITY

    def knows_person_question_bn(self, order: "Order") -> str:
        return (
            f"এই নম্বর থেকে আমাদের কাছে একটা {self.order_noun_bn} আছে — "
            f"{self.order_details_bn(order)}। আপনি কি {order.customer_name}-কে চিনেন?"
        )

    def relay_line_bn(self, order: "Order") -> str:
        action = "কনফার্ম" if self.key != "courier" else "রিসিভ"
        return (
            f"অনুগ্রহ করে {order.customer_name}-কে {self.order_noun_bn}টি {action} করতে বলবেন।"
        )

    def spoken_identity_instruction_bn(self, stage: str, order: "Order") -> str | None:
        """Exact next line for identity-gate stages, or None if this isn't one."""
        if stage == STAGE_IDENTITY:
            return f"হুবহু বলো: {self.opening_question_bn(order, None)}"
        if stage == STAGE_KNOWS_PERSON:
            return (
                f"হুবহু বলো: {self.knows_person_question_bn(order)} "
                "হ্যাঁ হলে knows_customer=true, না হলে knows_customer=false সেভ করো।"
            )
        if stage in (STAGE_RELAY, STAGE_WRONG_NUMBER):
            return "কিছু বলো না। এখনই end_call টুল কল করো।"
        return None

    def closing_line_bn(
        self,
        merchant: "Merchant",
        order: "Order",
        outcome: str,
        slots: dict[str, Any] | None = None,
    ) -> str:
        """Deterministic hang-up line. Spoken by end_call, not the LLM."""
        slots = slots or {}
        shop = merchant.business_name
        if outcome == "confirmed":
            return f"{shop}-এর সাথে থাকার জন্য ধন্যবাদ। ভালো থাকবেন।"
        if outcome == "cancelled":
            return f"ঠিক আছে। {shop}-এর সাথে থাকার জন্য ধন্যবাদ।"
        if outcome == "rescheduled":
            return "ঠিক আছে, ডেলিভারি পরে আবার শিডিউল করা হবে। ধন্যবাদ।"
        if outcome == "relay" or slots.get("knows_customer") is True:
            return self.relay_line_bn(order)
        if (
            outcome == "wrong_number"
            or slots.get("knows_customer") is False
            or slots.get("wrong_person")
        ):
            return "দুঃখিত, ভুল নম্বরে কল হয়ে গেছে। আপনার সময়ের জন্য ধন্যবাদ।"
        return "ধন্যবাদ, ভালো থাকবেন।"

    # ---- the derived state machine --------------------------------------

    def next_missing_stage(
        self, slots: dict[str, Any], settings: dict[str, bool], order: "Order"
    ) -> str:
        """Ordered cascade: the next thing the caller still owes.

        Skipping IS this function falling through a filled slot.
        """
        raise NotImplementedError

    def node_for_stage(self, stage: str) -> str:
        raise NotImplementedError

    def node_task_bn(self, node: str, order: "Order", merchant: "Merchant") -> str:
        """The node's instruction block (Bengali), appended on node change."""
        raise NotImplementedError

    def spoken_instruction_bn(
        self,
        stage: str,
        slots: dict[str, Any],
        settings: dict[str, bool],
        order: "Order",
        merchant: "Merchant",
    ) -> str:
        """Backend-owned wording of what the agent must say/ask next."""
        raise NotImplementedError

    def opening_question_bn(self, order: "Order", merchant: "Merchant | None" = None) -> str:
        """Speakable first question, played right after the TwiML greeting.

        Spoken deterministically (TTSSpeakFrame, no LLM round-trip) so the
        caller is engaged within seconds. Both flows start at the identity
        stage; a flow that starts elsewhere must override this.
        """
        return f"আমি কি {order.customer_name}-এর সাথে কথা বলছি?"

    # ---- prompt assembly -------------------------------------------------

    def system_facts_bn(
        self, order: "Order", merchant: "Merchant", settings: dict[str, bool]
    ) -> str:
        """The per-call facts block (who is being called and about what)."""
        raise NotImplementedError

    def terminals(self) -> list[Terminal]:
        raise NotImplementedError

    # ---- static (DTMF) variant ------------------------------------------

    def static_prompt_bn(self, order: "Order", merchant: "Merchant") -> list[str]:
        """Lines the static tier speaks before gathering a keypad digit."""
        raise NotImplementedError

    def static_digits(self, merchant: "Merchant") -> dict[str, tuple[str, str]]:
        """digit -> (spoken reply, outcome). Outcome '' = unrecognized."""
        raise NotImplementedError

    # ---- UI preview ------------------------------------------------------

    def preview_steps_bn(self, settings: dict[str, bool]) -> list[str]:
        """Ordered question list shown in Settings so merchants see the flow."""
        raise NotImplementedError


def build_node_directive_bn(flow: Flow, node: str, order: "Order", merchant: "Merchant") -> str:
    """The tail-appended step directive. Supersedes earlier step directives."""
    return (
        "ধাপ পরিবর্তন — এটি আগের সব ধাপ-নির্দেশনা বাতিল করে।\n"
        f"{flow.node_task_bn(node, order, merchant)}"
    ).strip()


def taka_bn(amount: Any) -> str:
    """Format an order amount for speech/prompt text."""
    try:
        return f"{float(amount):g}"
    except (TypeError, ValueError):
        return str(amount)
