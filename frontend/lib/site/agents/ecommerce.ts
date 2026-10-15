import { ShoppingBag } from "lucide-react";

import type { AgentSolution } from "../types";
import { EDIT_EVERY_LINE } from "./shared";

export const ecommerce: AgentSolution = {
  key: "ecommerce",
  slug: "ecommerce",
  name: "E-commerce",
  agentName: "Order confirmation caller",
  icon: ShoppingBag,
  forWho: "Online stores shipping cash-on-delivery orders",
  tagline: "Confirms cash-on-delivery orders before they ship.",
  summary:
    "Calls every cash-on-delivery customer before dispatch. It checks it has the right person, reads the order back, optionally confirms the address, and marks the order confirmed or cancelled, so you stop shipping parcels nobody accepts.",
  directions: "Outbound confirmation calls, in bulk or on a schedule",
  capabilities: [
    "Calls customers to confirm or cancel COD orders before dispatch",
    "Checks it's speaking with the person who placed the order",
    "Reads back items and total; optionally confirms the delivery address",
    "Retries unanswered calls and calls whole batches at once or on a daily schedule",
  ],
  setup: [
    "Your orders: customer, phone, items, total, delivery address",
    "Whether to double-check the delivery address",
    "When to call: one by one, the whole list, or automatically every day",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Confirmed", detail: "Ready to dispatch" },
    { label: "Cancelled", detail: "Don't ship — saved a return" },
    { label: "Wrong number", detail: "Order flagged before it leaves" },
    { label: "No answer", detail: "Retried automatically" },
    { label: "Needs review", detail: "Address change or a question for your team" },
  ],
  safety: [
    "Confirms identity before discussing an order",
    "Every call is recorded and transcribed, so you can check exactly what was agreed",
    "Transfers to your support line, or flags the order for a call-back, when the customer asks",
  ],
  example: {
    business: "Urban Threads",
    channel: "Outbound call",
    lines: [
      { who: "agent", text: "Hi, I'm calling from Urban Threads about your order. Am I speaking with Maya?" },
      { who: "caller", text: "Yes, that's me." },
      { who: "agent", text: "You ordered a blue hoodie in large, $48 cash on delivery. Shall we send it?" },
      { who: "caller", text: "Yes please." },
      { who: "agent", text: "And that's to 18 Pine Street, apartment 4?" },
      { who: "caller", text: "That's right." },
    ],
    result: { label: "Order confirmed", detail: "#1042 · ready to dispatch" },
  },
};
