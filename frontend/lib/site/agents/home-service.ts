import { Wrench } from "lucide-react";

import type { AgentSolution } from "../types";
import { CHAT_ADDONS, EDIT_EVERY_LINE } from "./shared";

export const homeService: AgentSolution = {
  key: "home_service",
  slug: "home-services",
  name: "Home services",
  agentName: "Dispatch line",
  icon: Wrench,
  forWho: "Plumbing, electrical, HVAC / AC, cleaning and appliance repair",
  tagline: "Takes the job, checks the area and books an arrival window.",
  summary:
    "Answers your service line while your crews are on the job. It takes the problem and the address, checks you cover the area, quotes your call-out charge and usual price range, and books an arrival window your teams can make. The day before, it calls to confirm.",
  directions: `Inbound calls, website chat and visit confirmation calls; ${CHAT_ADDONS}`,
  capabilities: [
    "Takes the job: service, problem description and address",
    "Checks the address against your service areas",
    "Quotes the call-out charge and usual price range from your service list",
    "Books a morning, afternoon or evening window within your teams' capacity",
    "Calls customers the day before to confirm, reschedule or cancel",
    "Skips what the caller already said — the problem and address in one breath is fine",
    "Texts the booking and window, with an optional link to pay the call-out charge",
  ],
  setup: [
    "Your services: name, category, call-out charge, usual price range, typical duration",
    "Service areas, working days and teams per arrival window",
    "Knowledge base: warranty, payment methods, what's priced separately",
    "How far ahead customers can book",
    EDIT_EVERY_LINE,
  ],
  outcomes: [
    { label: "Booked", detail: "Service, problem, address, window and call-out charge" },
    { label: "Confirmed", detail: "Customer confirmed on the day-before call" },
    { label: "Cancelled", detail: "Window released for another job" },
    { label: "Emergency", detail: "Safety instructions given, emergency number" },
    { label: "Call back", detail: "Out of area or needs a human decision" },
  ],
  safety: [
    "Gas leak, sparks, smoke or fire: gives the safety line and your emergency number first",
    "Quotes only your call-out charge and price range — never a fixed price for the repair",
    "Reads every booking back before it is saved",
    "Transfers to your dispatcher, or takes a message, when a caller asks for a person",
  ],
  example: {
    business: "FixRight Home Services",
    channel: "Inbound call",
    lines: [
      { who: "caller", text: "My AC is blowing warm air." },
      { who: "agent", text: "Sorry to hear that. What's the address for the visit?" },
      { who: "caller", text: "418 Bergen Street, Brooklyn." },
      { who: "agent", text: "We cover Brooklyn. The call-out charge is $89, and AC repairs usually run $120 to $450. Tomorrow 9 am to 12 pm is open. Shall I book it?" },
      { who: "caller", text: "Yes, book it." },
      { who: "agent", text: "Booked: AC repair at 418 Bergen Street, tomorrow between 9 and 12. We'll call the day before to confirm." },
    ],
    result: { label: "Visit booked", detail: "AC repair · tomorrow 9–12 · $89 call-out" },
  },
};
