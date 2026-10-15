import { Smile } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const dental: AgentSolution = {
  key: "dental",
  slug: "dental",
  name: "Dental practices",
  agentName: "Dental receptionist",
  icon: Smile,
  forWho: "General and family dentists, orthodontists and multi-chair practices",
  tagline: "Books checkups, asks about insurance and spots dental emergencies.",
  summary:
    "Answers your practice's phone day and night. It books with the dentist the patient wants, asks about their insurance, moves or cancels appointments and calls patients the day before. Severe swelling, a knocked-out tooth or bleeding that won't stop goes straight to your emergency line.",
  directions: `Inbound calls, website chat and reminder calls; ${CHAT_ADDONS}`,
  capabilities: [
    "Books checkups, cleanings and treatment from each dentist's days and hours",
    "Asks for the patient's insurance so your team can check it before the visit",
    "Spots dental emergencies and gives your emergency line first",
    "Finds an appointment by the caller's phone number to move or cancel it",
    "Calls patients the day before — they confirm, reschedule or cancel",
    "Skips what the caller already said and texts a confirmation once it's booked",
  ],
  setup: [
    "Your dentists and hygienists: days, hours, minutes per patient, fee",
    "Your emergency or on-call number",
    "Knowledge base: insurance plans accepted, new-patient forms, payment options",
    "Optional steps: new or returning patient, online payment, staff approval before confirming",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Booked", detail: "Dentist, time, patient and insurance" },
    { label: "Rescheduled", detail: "Moved to a new time, old slot released" },
    { label: "Cancelled", detail: "Slot freed for another patient" },
    { label: "Confirmed", detail: "Patient confirmed on the reminder call" },
    { label: "Emergency", detail: "Caller sent to your emergency line" },
    { label: "Needs follow-up", detail: "Anything your team should look at" },
  ],
  safety: [
    "Never diagnoses or suggests treatment",
    "Dental emergencies: gives your emergency line straight away",
    "Never confirms insurance coverage — it notes the plan for your team",
    "Reads every booking back before it is saved",
    "Transfers to your front desk, or takes a message, when a caller asks for a person",
  ],
  example: {
    business: "Bright Smile Dental",
    channel: "Inbound call",
    lines: [
      { who: "agent", text: "Thanks for calling Bright Smile Dental. How can I help?" },
      { who: "caller", text: "I need a cleaning with Dr. Patel next Tuesday. It's for Emma Brooks." },
      { who: "agent", text: "Dr. Patel has Tuesday at 9:30 am or 2:00 pm. Which suits you?" },
      { who: "caller", text: "2 pm." },
      { who: "agent", text: "And which dental insurance do you have?" },
      { who: "caller", text: "Summit Dental, through work." },
      { who: "agent", text: "Emma Brooks with Dr. Patel, Tuesday at 2:00 pm, Summit Dental. Shall I book it?" },
      { who: "caller", text: "Yes, please." },
    ],
    result: { label: "Appointment booked", detail: "Dr. Patel · Tue 2:00 pm · confirmation texted" },
  },
};
