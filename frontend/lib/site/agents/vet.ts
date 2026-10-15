import { PawPrint } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const vet: AgentSolution = {
  key: "vet",
  slug: "veterinary",
  name: "Veterinary clinics",
  agentName: "Vet clinic receptionist",
  icon: PawPrint,
  forWho: "Small-animal practices, mobile vets and animal hospitals",
  tagline: "Books visits for every pet and sends emergencies to the emergency vet.",
  summary:
    "Answers your clinic's phone for pet owners. It books with the vet they want, takes the owner's and pet's details, moves or cancels appointments and calls the day before. Poisoning, breathing trouble or a road accident goes straight to your emergency vet.",
  directions: `Inbound calls, website chat and reminder calls; ${CHAT_ADDONS}`,
  capabilities: [
    "Books with each vet from their days, hours and minutes per visit",
    "Takes the owner's name, the pet's name and species",
    "Spots animal emergencies — poisoning, breathing trouble, seizures, heavy bleeding — and gives your emergency vet first",
    "Finds an appointment by the owner's phone number to move or cancel it",
    "Calls owners the day before with a reminder that names the pet",
    "Skips what the owner already said — “my beagle Max” gives the pet's name and species",
    "Texts a confirmation, with an optional link to pay online",
  ],
  setup: [
    "Your vets: days, hours, minutes per visit, daily limit, fee",
    "Your emergency vet or out-of-hours number",
    "Knowledge base: vaccinations, species you treat, payment and pet insurance",
    "Optional steps: new or returning client, online payment, staff approval",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Booked", detail: "Vet, time, owner and pet" },
    { label: "Rescheduled", detail: "Moved to a new time, old slot released" },
    { label: "Cancelled", detail: "Slot freed for another patient" },
    { label: "Confirmed", detail: "Owner confirmed on the reminder call" },
    { label: "Emergency", detail: "Owner sent to the emergency vet" },
    { label: "Needs follow-up", detail: "Anything your team should look at" },
  ],
  safety: [
    "Never gives veterinary advice or a diagnosis",
    "Animal emergencies: gives your emergency vet number before anything else",
    "Reads every booking back before it is saved",
    "Transfers to your front desk, or takes a message, when an owner asks for a person",
  ],
  example: {
    business: "Oak Hollow Vets",
    channel: "Inbound call",
    lines: [
      { who: "agent", text: "Thanks for calling Oak Hollow Vets. How can I help?" },
      { who: "caller", text: "My beagle Max is due for his vaccinations." },
      { who: "agent", text: "Happy to book Max in. Dr. Nguyen has Thursday at 4:15 pm. Does that work?" },
      { who: "caller", text: "Perfect. I'm Sam Turner." },
      { who: "agent", text: "Max the beagle, owner Sam Turner, with Dr. Nguyen on Thursday at 4:15 pm. Shall I book it?" },
      { who: "caller", text: "Yes, please." },
      { who: "agent", text: "Booked. I'll text you the details, and we'll call the day before." },
    ],
    result: { label: "Appointment booked", detail: "Max · Dr. Nguyen · Thu 4:15 pm" },
  },
};
