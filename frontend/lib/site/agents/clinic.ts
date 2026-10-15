import { Stethoscope } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const clinic: AgentSolution = {
  key: "clinic",
  slug: "clinics",
  name: "Clinics & doctors",
  agentName: "Clinic receptionist",
  icon: Stethoscope,
  forWho: "Family practices, specialist chambers and physio clinics",
  tagline: "Books, moves and reminds — straight from your doctor list.",
  summary:
    "Answers your clinic's phone around the clock. It books from your doctor list, moves or cancels appointments by the caller's number, answers questions on doctors, hours, fees and insurance, and calls patients the day before to confirm.",
  directions: `Inbound calls, website chat and reminder calls; ${CHAT_ADDONS}`,
  capabilities: [
    "Books appointments from each doctor's days, hours and minutes per patient",
    "Finds a caller's existing appointment by phone number to move or cancel it",
    "Answers questions on doctors, specialties, hours, fees and insurance from your knowledge base",
    "Calls patients with reminders — they confirm, reschedule or cancel on the call",
    "Respects daily patient limits, how far ahead you book and the earliest bookable time",
    "Skips what the caller already said — “Dr. Carter on Wednesday” answers two questions",
    "Texts a confirmation, with an optional link to pay the fee online",
  ],
  setup: [
    "Your doctors: name, specialty, days, start and end time, minutes per patient, daily limit, fee",
    "Knowledge base: insurance accepted, parking, reports, preparation instructions",
    "Booking rules: how many days ahead and how soon patients can book",
    "Optional health advice line for medical questions",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Booked", detail: "New appointment with doctor, time and reason" },
    { label: "Rescheduled", detail: "Moved to a new time, old slot released" },
    { label: "Cancelled", detail: "Slot freed for another patient" },
    { label: "Confirmed", detail: "Patient confirmed on the reminder call" },
    { label: "Emergency", detail: "Caller sent to the emergency number" },
    { label: "Needs follow-up", detail: "Anything your team should look at" },
  ],
  safety: [
    "Never gives medical advice or interprets symptoms",
    "Emergencies: tells the caller to hang up and call your local emergency number",
    "Reads every booking back before it is saved",
    "Transfers to your front desk, or takes a message, when a caller asks for a person",
  ],
  example: {
    business: "CityCare Family Clinic",
    channel: "Inbound call",
    lines: [
      { who: "agent", text: "Thanks for calling CityCare Family Clinic. How can I help?" },
      { who: "caller", text: "Hi, I'd like my son to see the pediatrician this week." },
      { who: "agent", text: "Dr. James Carter sees children Monday, Wednesday and Friday, 10 am to 4 pm. The first opening is Wednesday at 10:40 am. Does that work?" },
      { who: "caller", text: "Wednesday's good." },
      { who: "agent", text: "Let me read that back: Leo Garcia with Dr. Carter, Wednesday at 10:40 am. The consultation fee is $140. Shall I book it?" },
      { who: "caller", text: "Yes, please." },
      { who: "agent", text: "You're booked. We'll call the day before to remind you." },
    ],
    result: { label: "Appointment booked", detail: "Dr. Carter · Wed 10:40 am · reminder scheduled" },
  },
};
