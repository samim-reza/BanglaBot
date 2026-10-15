import { UtensilsCrossed } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const restaurant: AgentSolution = {
  key: "restaurant",
  slug: "restaurants",
  name: "Restaurants",
  agentName: "Orders & reservations line",
  icon: UtensilsCrossed,
  forWho: "Restaurants, pizzerias, takeaways, cafés and delivery kitchens",
  tagline: "Takes phone orders and table bookings, priced from your menu.",
  summary:
    "Answers the phone through the dinner rush. It takes pickup and delivery orders from your menu, with sizes and extras, adds tax and the delivery fee and reads the total back. It also books tables by party size and tells callers where their order is.",
  directions: `Inbound calls and website chat; ${CHAT_ADDONS}`,
  capabilities: [
    "Takes pickup and delivery orders from your menu, with sizes, extras and notes",
    "Works out every total from your prices: options, tax, delivery fee and minimum order",
    "Books tables by party size within your covers per slot; big groups go to your team",
    "Tells callers the status of their latest order, found by phone number",
    "Skips what the caller already said — “two large pepperoni for delivery” fills the order and the type",
    "Texts the order or booking, with an optional online payment link",
  ],
  setup: [
    "Your menu: items, prices, categories, options like size and extras, allergens",
    "Opening hours, prep and delivery times, delivery fee, minimum order, tax rate",
    "Tables: largest party, covers per slot, how far ahead guests can book",
    "Optional: online payment, a table deposit, a suggested add-on before checkout",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Order placed", detail: "Items, options, pickup or delivery, total and time" },
    { label: "Table booked", detail: "Party size, day, time and guest name" },
    { label: "Awaiting payment", detail: "Held until the payment link is paid" },
    { label: "Status given", detail: "Caller told where their order is" },
    { label: "Message taken", detail: "Large groups, catering or anything for your team" },
  ],
  safety: [
    "Totals come from your menu prices, never from the AI",
    "Mentions only the allergens you list — never promises a dish is safe",
    "Takes orders and bookings only for times you're open",
    "Reads every order and booking back before it is saved",
    "Transfers to your staff, or takes a message, when a caller asks for a person",
  ],
  example: {
    business: "Bella Napoli Pizzeria",
    channel: "Inbound call",
    lines: [
      { who: "agent", text: "Thanks for calling Bella Napoli. Is this for pickup, delivery or a table?" },
      { who: "caller", text: "Delivery, please. Two large pepperoni and a Caesar salad." },
      { who: "agent", text: "Two large pepperoni and one Caesar salad for delivery. What's the address?" },
      { who: "caller", text: "22 Elm Street, apartment 3B." },
      { who: "agent", text: "That's $50.44 with tax and the $4 delivery fee, about 45 minutes. Shall I place it?" },
      { who: "caller", text: "Yes, go ahead." },
      { who: "agent", text: "Done. I'll text you the order, with a link if you'd like to pay now." },
    ],
    result: { label: "Delivery order placed", detail: "3 items · $50.44 · about 45 min" },
  },
};
