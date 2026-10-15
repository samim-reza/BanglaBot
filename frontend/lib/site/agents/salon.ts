import { Scissors } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const salon: AgentSolution = {
  key: "salon",
  slug: "salons-spas",
  name: "Salons & spas",
  agentName: "Salon front desk",
  icon: Scissors,
  forWho: "Hair salons, barbershops, nail studios, spas and massage studios",
  tagline: "Books the right service with the right stylist, deposit included.",
  summary:
    "Answers your salon's phone while everyone's with a client. It books each service with the stylist the client asks for, or whoever's free, fits it into their hours, and moves or cancels bookings. It can take a deposit and read out your cancellation policy.",
  directions: `Inbound calls and website chat; ${CHAT_ADDONS}`,
  capabilities: [
    "Books by service and stylist or therapist, or the first one free",
    "Fits each service's length into that person's hours — no overlaps",
    "Moves or cancels a client's booking, found by their phone number",
    "Takes a deposit by texted payment link and holds the slot until it's paid",
    "Reads out your cancellation policy before it confirms",
    "Skips what the client already said — “a cut with Jess on Friday” answers three questions",
    "Texts a confirmation the moment it's booked",
  ],
  setup: [
    "Your services: name, length, price and who performs them",
    "Your team: stylists or therapists, their days and hours",
    "Deposit amount, how long a slot is held, and your cancellation policy",
    "Knowledge base: products, parking, aftercare, prices that vary",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Booked", detail: "Service, stylist, day, time and client" },
    { label: "Awaiting deposit", detail: "Slot held until the payment link is paid" },
    { label: "Rescheduled", detail: "Moved to a new time, old slot released" },
    { label: "Cancelled", detail: "Slot freed for another client" },
    { label: "Needs follow-up", detail: "Anything your team should look at" },
  ],
  safety: [
    "Quotes only your listed prices and lengths",
    "Answers only from your service list and knowledge base",
    "Reads every booking back before it is saved",
    "Transfers to your front desk, or takes a message, when a client asks for a person",
  ],
  example: {
    business: "Willow & Co. Salon",
    channel: "Website chat",
    lines: [
      { who: "caller", text: "Hi! Can I book a cut and blow-dry with Jess on Friday?" },
      { who: "agent", text: "Jess has Friday at 11:00 am or 3:30 pm. A cut and blow-dry takes an hour and is $75. Which works?" },
      { who: "caller", text: "3:30 please. I'm Priya, 555-0142." },
      { who: "agent", text: "Thanks, Priya. There's a $20 deposit, and we ask for 24 hours' notice to cancel. Is that OK?" },
      { who: "caller", text: "Sure." },
      { who: "agent", text: "Booked: cut and blow-dry with Jess, Friday at 3:30 pm. I've texted you the deposit link." },
    ],
    result: { label: "Booked · awaiting deposit", detail: "Jess · Fri 3:30 pm · $20 link sent" },
  },
};
