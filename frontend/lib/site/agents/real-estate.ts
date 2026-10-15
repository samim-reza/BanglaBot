import { Building2 } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const realEstate: AgentSolution = {
  key: "real_estate",
  slug: "real-estate",
  name: "Real estate agencies",
  agentName: "Leasing & sales assistant",
  icon: Building2,
  forWho: "Sales and rental agencies, brokers, property managers",
  tagline: "Qualifies every caller, books viewings and scores the lead.",
  summary:
    "Picks up for buyers, renters and sellers. It asks their budget, area, property type and timeline, presents up to two matching listings, books a viewing and scores every lead hot, warm or cold, so your agents call the right people first.",
  directions: `Inbound calls, website chat and lead follow-up calls; ${CHAT_ADDONS}`,
  capabilities: [
    "Qualifies buyers, renters and sellers: budget, area, type, bedrooms, timeline",
    "Presents up to two matching listings from your own inventory",
    "Books property viewings within your viewing days, hours and capacity",
    "Scores every lead hot, warm or cold with fixed rules — not a guess",
    "Calls leads back to follow up and book the next step",
    "Skips what the caller already said — “a 2-bed to buy in Riverside” covers three questions",
    "Texts the viewing details as soon as it's booked",
  ],
  setup: [
    "Your listings: title, sale or rent, type, area, size, price, bedrooms, highlights",
    "Viewing days, hours, minutes per viewing and how many at once",
    "Knowledge base: fees, required documents, how the process works",
    "Who takes over for negotiation and offers",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Visit booked", detail: "Viewing time, listing and contact details" },
    { label: "Lead captured", detail: "Intent, budget, area and a hot / warm / cold score" },
    { label: "Follow up", detail: "Interested, but not ready to book yet" },
    { label: "Not interested", detail: "Closed out so nobody chases it" },
    { label: "Transferred", detail: "Handed to an agent for negotiation" },
  ],
  safety: [
    "Never promises a price, discount or availability beyond your listing data",
    "Never states legal status, title or planning facts it hasn't been given",
    "Hands negotiation and offers to a human agent",
    "Reads every viewing back before it is saved",
  ],
  example: {
    business: "Keystone Realty",
    channel: "Inbound call",
    lines: [
      { who: "caller", text: "I'm looking to buy a two-bedroom near Riverside, up to about $350,000." },
      { who: "agent", text: "Got it — two bedrooms to buy in Riverside, up to $350,000. When are you hoping to move?" },
      { who: "caller", text: "Within the next three months." },
      { who: "agent", text: "One listing fits: a 2-bed apartment at Riverside Towers, 1,150 sq ft with a river view, listed at $329,000. Would you like to see it?" },
      { who: "caller", text: "Yes, this weekend if possible." },
      { who: "agent", text: "I can show it Saturday at 11 am or 2 pm." },
      { who: "caller", text: "11 works." },
    ],
    result: { label: "Viewing booked · Hot lead", detail: "Riverside Towers · Sat 11:00 am" },
  },
};
