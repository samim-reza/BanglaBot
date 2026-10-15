import { Blocks } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const custom: AgentSolution = {
  key: "custom",
  slug: "custom",
  name: "Any other business",
  agentName: "Custom agent",
  icon: Blocks,
  forWho: "Studios, tutors, rentals, repair shops, agencies — any business that books or takes inquiries",
  tagline: "Build your own: your questions, your bookings, your rules.",
  summary:
    "Not on the list? Build the agent yourself. Choose the questions it asks, what callers can book and when, whether they pay online and whether your team approves each booking. It takes inquiries and messages too.",
  directions: `Inbound calls and website chat; ${CHAT_ADDONS}`,
  capabilities: [
    "Asks your own intake questions, in your order",
    "Books what you offer — rooms, classes, people, equipment — within its days, hours and capacity",
    "Takes inquiries as leads and messages for your team",
    "Optional online payment by texted link, and staff approval before a booking is confirmed",
    "Skips questions the caller has already answered",
    "Texts a confirmation once it's booked",
  ],
  setup: [
    "What can be booked: name, days, hours, minutes per booking, how many at once, price",
    "Your questions: what to ask every caller, beyond name and phone",
    "Booking rules: how many days ahead and how soon people can book",
    "Payment and approval: on or off",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Booked", detail: "What, when and the answers to your questions" },
    { label: "Awaiting payment", detail: "Held until the payment link is paid" },
    { label: "Awaiting approval", detail: "Waiting for your team to approve" },
    { label: "Lead captured", detail: "An inquiry with the details you asked for" },
    { label: "Message taken", detail: "Passed on to your team" },
  ],
  safety: [
    "Answers only from your knowledge base — if it isn't there, it says so",
    "Doesn't confirm a booking that needs approval until your team approves it",
    "Reads every booking back before it is saved",
    "Transfers to your team, or takes a message, when a caller asks for a person",
  ],
  example: {
    business: "Northside Pottery Studio",
    channel: "Inbound call",
    lines: [
      { who: "agent", text: "Hi, you've reached Northside Pottery Studio. How can I help?" },
      { who: "caller", text: "I'd like to book a wheel class on Saturday. I'm Dana Lee." },
      { who: "agent", text: "Thanks, Dana. The two-hour wheel class has Saturday at 10 am or 1 pm, $45. Which would you like?" },
      { who: "caller", text: "10 am." },
      { who: "agent", text: "Have you thrown on a wheel before?" },
      { who: "caller", text: "No, total beginner." },
      { who: "agent", text: "Wheel class, Saturday at 10 am, $45, beginner. I'll text you a payment link to confirm your spot." },
    ],
    result: { label: "Booked · awaiting payment", detail: "Wheel class · Sat 10 am · beginner" },
  },
};
