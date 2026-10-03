/** Static copy for the public website: agents, features, plans, add-ons, FAQs.
 *
 * Plan and add-on numbers mirror backend/app/core/plans.py — change both together.
 * The product name always comes from BRAND (lib/brand.ts).
 */

import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  BookOpen,
  Building2,
  CalendarCheck,
  CalendarClock,
  CalendarSync,
  Globe,
  ListChecks,
  MessageSquare,
  MessageSquareText,
  MonitorPlay,
  PhoneCall,
  PhoneForwarded,
  ShoppingBag,
  Stethoscope,
  Webhook,
  Wrench,
  Zap,
} from "lucide-react";

import { BRAND } from "@/lib/brand";

/* ------------------------------------------------------------------ navigation */

export const SITE_NAV = [
  { href: "/solutions", label: "Solutions" },
  { href: "/pricing", label: "Pricing" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/contact", label: "Contact sales" },
] as const;

export const TRIAL_HREF = "/contact?plan=trial";
export const SALES_HREF = "/contact";

/* ------------------------------------------------------------------ agents */

/** Matches the backend's vertical keys (also used as ?type= on the contact form). */
export type AgentKey = "clinic" | "real_estate" | "home_service" | "ecommerce";

export type ChatLine = { who: "agent" | "caller"; text: string };

export type ExampleConversation = {
  business: string;
  channel: "Inbound call" | "Outbound call" | "Website chat";
  lines: ChatLine[];
  result: { label: string; detail: string };
};

export type AgentSolution = {
  key: AgentKey;
  /** URL segment under /solutions. */
  slug: string;
  name: string;
  agentName: string;
  icon: LucideIcon;
  forWho: string;
  tagline: string;
  summary: string;
  directions: string;
  capabilities: string[];
  setup: string[];
  outcomes: { label: string; detail: string }[];
  safety: string[];
  example: ExampleConversation;
};

export const AGENTS: AgentSolution[] = [
  {
    key: "clinic",
    slug: "clinics",
    name: "Clinics & doctors",
    agentName: "Clinic receptionist",
    icon: Stethoscope,
    forWho: "Family practices, specialist chambers, dental and physio clinics",
    tagline: "Books, moves and reminds — straight from your doctor list.",
    summary:
      "Answers the clinic phone and website chat around the clock. It books appointments from your doctor list, moves or cancels them for callers by their phone number, answers questions about doctors, hours, fees and insurance, and calls patients the day before to confirm.",
    directions: "Inbound calls, website chat and reminder calls",
    capabilities: [
      "Books appointments from each doctor's days, hours and minutes per patient",
      "Finds a caller's existing appointment by phone number to move or cancel it",
      "Answers questions on doctors, specialties, hours, fees and insurance from your knowledge base",
      "Calls patients with reminders — they confirm, reschedule or cancel on the call",
      "Respects daily patient limits, how far ahead you book and the earliest bookable time",
    ],
    setup: [
      "Your doctors: name, specialty, days, start and end time, minutes per patient, daily limit, fee",
      "Knowledge base: insurance accepted, parking, reports, preparation instructions",
      "Booking rules: how many days ahead and how soon patients can book",
      "Optional health advice line for medical questions",
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
  },
  {
    key: "real_estate",
    slug: "real-estate",
    name: "Real estate agencies",
    agentName: "Leasing & sales assistant",
    icon: Building2,
    forWho: "Sales and rental agencies, brokers, property managers",
    tagline: "Qualifies every caller, books viewings and scores the lead.",
    summary:
      "Picks up for buyers, renters and sellers. It asks what they need — budget, area, property type, timeline — presents up to two matching listings from your inventory, books a viewing and scores every lead hot, warm or cold so your agents call the right people first.",
    directions: "Inbound calls, website chat and lead follow-up calls",
    capabilities: [
      "Qualifies buyers, renters and sellers: budget, area, type, bedrooms, timeline",
      "Presents up to two matching listings from your own inventory",
      "Books property viewings within your viewing days, hours and capacity",
      "Scores every lead hot, warm or cold with fixed rules — not a guess",
      "Calls leads back to follow up and book the next step",
    ],
    setup: [
      "Your listings: title, sale or rent, type, area, size, price, bedrooms, highlights",
      "Viewing days, hours, minutes per viewing and how many at once",
      "Knowledge base: fees, required documents, how the process works",
      "Who takes over for negotiation and offers",
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
  },
  {
    key: "home_service",
    slug: "home-services",
    name: "Home services",
    agentName: "Dispatch line",
    icon: Wrench,
    forWho: "Plumbing, electrical, HVAC / AC, cleaning and appliance repair",
    tagline: "Takes the job, checks the area and books an arrival window.",
    summary:
      "Answers your service line while your crews are on the job. It takes the service, the problem and the address, checks you cover the area, quotes the call-out charge and usual price range, and books an arrival window your teams can actually make. The day before, it calls to confirm.",
    directions: "Inbound calls, website chat and visit confirmation calls",
    capabilities: [
      "Takes the job: service, problem description and address",
      "Checks the address against your service areas",
      "Quotes the call-out charge and usual price range from your service list",
      "Books a morning, afternoon or evening window within your teams' capacity",
      "Calls customers the day before to confirm, reschedule or cancel",
    ],
    setup: [
      "Your services: name, category, call-out charge, usual price range, typical duration",
      "Service areas, working days and teams per arrival window",
      "Knowledge base: warranty, payment methods, what's priced separately",
      "How far ahead customers can book",
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
  },
  {
    key: "ecommerce",
    slug: "ecommerce",
    name: "E-commerce",
    agentName: "Order confirmation caller",
    icon: ShoppingBag,
    forWho: "Online stores shipping cash-on-delivery orders",
    tagline: "Confirms cash-on-delivery orders before they ship.",
    summary:
      "Calls every cash-on-delivery customer before dispatch. It checks it's speaking to the right person, reads the order back, optionally confirms the delivery address, and marks the order confirmed or cancelled — so you stop paying to ship parcels nobody accepts.",
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
  },
];

export function agentBySlug(slug: string): AgentSolution | undefined {
  return AGENTS.find((agent) => agent.slug === slug);
}

/* ------------------------------------------------------------------ platform */

export type Feature = { icon: LucideIcon; title: string; body: string };

export const FEATURES: Feature[] = [
  {
    icon: PhoneCall,
    title: "A real phone number, both ways",
    body: "Your agent answers inbound calls and places outbound ones on a real number. Use ours, or forward your existing line to it.",
  },
  {
    icon: MessageSquare,
    title: "Website chat with one script tag",
    body: "The same agent, typed. Paste one line into your site and visitors can book from the chat bubble.",
  },
  {
    icon: BookOpen,
    title: "Answers only from your data",
    body: "Replies come from your catalog and knowledge base. If the answer isn't there, the agent says so instead of guessing.",
  },
  {
    icon: ListChecks,
    title: "Read-back before every booking",
    body: "Name, time, price and details are read back and confirmed before anything is written to your records.",
  },
  {
    icon: CalendarCheck,
    title: "No double bookings",
    body: "Slots are checked against your schedule, capacity and your own calendar at the moment of booking, across phone and chat.",
  },
  {
    icon: MessageSquareText,
    title: "Text confirmations & reminders",
    body: "Callers get an SMS with the date, time and details as soon as they book, another if it changes, and a reminder before — fewer no-shows.",
  },
  {
    icon: CalendarSync,
    title: "Syncs with your calendar",
    body: "Bookings appear in Google Calendar the moment they're made, or in Outlook and Apple via a private feed. Busy times there are never offered.",
  },
  {
    icon: PhoneForwarded,
    title: "Live transfer to your team",
    body: "When a caller asks for a person — or the agent shouldn't handle it — the call goes straight to your staff.",
  },
  {
    icon: AudioLines,
    title: "Recordings, transcripts, outcomes",
    body: "Every call is recorded and transcribed, with a clear outcome: booked, rescheduled, cancelled, lead, follow-up.",
  },
  {
    icon: CalendarClock,
    title: "Bulk & scheduled campaigns",
    body: "Call a whole list at once or every day at a set time — reminders, confirmations and lead follow-ups.",
  },
  {
    icon: Webhook,
    title: "Webhooks into your systems",
    body: "Every booking and outcome can be pushed to your practice software, CRM or spreadsheet automation.",
  },
  {
    icon: Globe,
    title: "Your region, your language",
    body: "Currency, time zone, emergency number, phone format and English accent per account. English today, Bangla available.",
  },
  {
    icon: Zap,
    title: "Fast, natural turns",
    body: "Scripted lines play from a voice cache and each turn takes a single AI round-trip, so callers aren't left waiting.",
  },
  {
    icon: MonitorPlay,
    title: "Test console",
    body: "Call your agent from the browser or chat with it before going live. See exactly what it would book.",
  },
];

export type Step = { title: string; body: string; points: string[] };

export const STEPS: Step[] = [
  {
    title: "Pick your business type",
    body: "Clinic, real estate, home services or e-commerce. Your agent arrives with its conversation flow, booking rules and safety rules already built.",
    points: ["Set once, when your account is created", "Region sets currency, time zone and emergency number"],
  },
  {
    title: "Add your doctors, listings or services",
    body: "Fill in what you offer and when, then paste your FAQs, policies and prices into the knowledge base.",
    points: ["Days, hours, capacity and prices", "Insurance, service areas, fees, documents"],
  },
  {
    title: "Test it in your browser",
    body: "Call your agent from the test console or chat with it. Every test call is transcribed, so you see exactly what it said and booked.",
    points: ["No phone needed to try it", "Tweak your greeting and knowledge, test again"],
  },
  {
    title: "Go live on your number and website",
    body: "Point calls at your agent's number and paste one script tag for the chat widget. Bookings start landing in your portal.",
    points: ["Forward after hours or around the clock", "Reminder and follow-up calls on your schedule"],
  },
];

/* ------------------------------------------------------------------ pricing */

export const TRIAL = { days: 14, minutes: 50 } as const;

export type SitePlan = {
  key: "starter" | "growth" | "pro";
  name: string;
  price: number;
  minutes: number;
  chats: number;
  /** Texts (SMS confirmations + reminders) included each month. */
  sms: number;
  numbers: number;
  overage: number;
  tagline: string;
  features: string[];
  highlight: boolean;
};

export const PLANS: SitePlan[] = [
  {
    key: "starter",
    name: "Starter",
    price: 49,
    minutes: 150,
    chats: 100,
    sms: 100,
    numbers: 1,
    overage: 0.3,
    tagline: "Never miss a call again — for a single practice, shop or crew.",
    features: [
      "1 phone number",
      "150 call minutes / month (inbound + outbound)",
      "100 website chats / month",
      "Booking, leads and call recordings",
      "Doctor / listing / service catalog",
      "100 SMS confirmations & reminders",
      "Calendar feed (Google, Outlook, Apple)",
      "Email support",
    ],
    highlight: false,
  },
  {
    key: "growth",
    name: "Growth",
    price: 149,
    minutes: 600,
    chats: 500,
    sms: 500,
    numbers: 2,
    overage: 0.22,
    tagline: "For busy front desks: answers, books and calls back.",
    features: [
      "Everything in Starter",
      "2 phone numbers",
      "600 call minutes / month",
      "500 website chats / month",
      "Reminder & confirmation calls",
      "500 SMS confirmations & reminders",
      "Two-way Google Calendar sync",
      "Webhooks into your systems",
      "Live transfer to your team",
    ],
    highlight: true,
  },
  {
    key: "pro",
    name: "Pro",
    price: 349,
    minutes: 1800,
    chats: 2000,
    sms: 2000,
    numbers: 3,
    overage: 0.16,
    tagline: "For multi-location clinics, agencies and service fleets.",
    features: [
      "Everything in Growth",
      "3 phone numbers",
      "1,800 call minutes / month",
      "2,000 website chats / month",
      "Bulk & scheduled outbound campaigns",
      "2,000 SMS confirmations & reminders",
      "Priority support and onboarding",
    ],
    highlight: false,
  },
];

export const ENTERPRISE = {
  name: "Enterprise",
  priceFrom: 999,
  tagline: "Custom volume, locations, SLAs and integrations.",
  features: ["Volume minutes from $0.10", "Unlimited locations", "Custom integrations & SSO", "Dedicated success manager"],
} as const;

/** Annual billing = 2 months free: pay 10 months, get 12. */
export function annualMonthly(price: number): number {
  return Math.round((price * 10) / 12);
}

export function annualTotal(price: number): number {
  return price * 10;
}

export function usd(value: number, decimals = 0): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export const ADDONS = [
  { key: "number", name: "Extra phone number", price: "$5 / mo", note: "US & Canada; $10 UK / Australia" },
  { key: "location", name: "Extra location or agent", price: "$49 / mo", note: "A second clinic, office or brand" },
  { key: "language", name: "Extra language", price: "$19 / mo", note: "Bangla today; more coming" },
  { key: "chat", name: "Chat-only plan", price: "$29 / mo", note: "Website chat widget, 500 conversations" },
  { key: "recording", name: "Extended recording retention", price: "$10 / mo", note: "Keep call recordings for 12 months" },
  { key: "sms", name: "Extra texts", price: "$10 / 500", note: "SMS beyond your plan's included texts (US & Canada)" },
  { key: "setup", name: "Done-for-you setup", price: "$299 once", note: "We load your catalog, script and number" },
  { key: "cod", name: "COD order confirmation", price: "$0.20 / answered call", note: "E-commerce, US / UK / Canada" },
] as const;

export const COMPARISON = [
  {
    option: "Full-time receptionist",
    cost: "~$3,100 / month",
    unit: "wages for one shift",
    detail: "One shift, five days a week. Benefits, breaks, sick days and evenings are extra.",
    ours: false,
  },
  {
    option: "Live answering service",
    cost: "~$3.45–$5 / minute",
    unit: "e.g. $250 for 50 minutes",
    detail: "Takes messages well; usually can't book into your schedule or call customers back.",
    ours: false,
  },
  {
    option: "Developer voice platforms",
    cost: "$0.07–$0.31 / minute",
    unit: "plus engineering",
    detail: "You build the flows, booking logic, telephony and safety rules yourself — and maintain them.",
    ours: false,
  },
  {
    option: `${BRAND.name} Growth`,
    cost: "≈ $0.25 / minute",
    unit: "$149 for 600 minutes",
    detail: "Ready-made agent that answers 24/7, books into your records and calls back.",
    ours: true,
  },
] as const;

export const COMPARISON_SOURCES =
  "Receptionist: U.S. Bureau of Labor Statistics, Occupational Employment and Wage Statistics, receptionists and information clerks, median annual wage $37,230 (May 2024) ÷ 12 months; wages only. Answering service: published per-minute plan prices, e.g. Ruby's 50-minute plan at $250. Developer platforms: published per-minute list prices of developer voice-AI platforms, before telephony and engineering time. Vendor prices change; check current rates.";

/* ------------------------------------------------------------------ FAQs */

export type Faq = { q: string; a: string };

export const HOME_FAQS: Faq[] = [
  {
    q: "Where does the agent get its answers?",
    a: "Only from what you give it: your doctor, listing or service catalog and your knowledge base. If a caller asks something that isn't covered, the agent says it doesn't know, offers to take a message or transfers the call — it doesn't make things up.",
  },
  {
    q: "Can I keep my existing phone number?",
    a: "Yes. You get a real number for your agent; forward your existing line to it around the clock, after hours only, or when your team doesn't pick up.",
  },
  {
    q: "Where do bookings go?",
    a: "Straight into your records in the portal — appointments, viewings or service visits — with double-booking protection. On Growth and above, webhooks push every booking and outcome into your own systems.",
  },
  {
    q: "What happens when a caller needs a real person?",
    a: "On Growth and above the agent transfers the call live to your team. Otherwise it takes the details and marks the call for follow-up so nobody slips through.",
  },
  {
    q: "Which languages does it speak?",
    a: "English today, with the accent set per account. Bangla is available as an extra language, with more on the way.",
  },
  {
    q: "How much work is setup?",
    a: "Add your doctors, listings or services, paste your FAQs, and test in the browser. Prefer not to? Our done-for-you setup loads your catalog, script and number for a one-time $299.",
  },
  {
    q: "Is there a free trial?",
    a: `Yes — ${TRIAL.days} days with ${TRIAL.minutes} call minutes, the browser test console and the website chat widget included.`,
  },
];

export const PRICING_FAQS: Faq[] = [
  {
    q: "What counts as a call minute?",
    a: "Connected call time — the time a caller is actually on the line with your agent. Inbound and outbound minutes come from the same pool.",
  },
  {
    q: "What counts as a website chat?",
    a: "A conversation in which the visitor wrote at least one message. Opening the chat bubble and closing it again doesn't count.",
  },
  {
    q: "What happens if I go over my minutes?",
    a: "Your agent keeps answering. Extra minutes are billed per minute at your plan's overage rate: $0.30 on Starter, $0.22 on Growth, $0.16 on Pro.",
  },
  {
    q: "Are text messages included?",
    a: "Yes. Every plan includes SMS confirmations and reminders: 100 a month on Starter, 500 on Growth and 2,000 on Pro. Extra texts are $10 per 500. A long message can use more than one text.",
  },
  {
    q: "Which calendars do you work with?",
    a: "Google Calendar connects both ways on Growth and Pro: bookings appear instantly and your busy times are never offered. Outlook, Apple and any other calendar can subscribe to your private booking feed and share their busy times through an iCal link.",
  },
  {
    q: "Do international calls cost more?",
    a: "Outbound calls to international numbers can use more than one included minute per minute on expensive routes. If you call abroad often, talk to sales about volume rates.",
  },
  {
    q: "How does annual billing work?",
    a: "Pay for 10 months and get 12 — two months free. The monthly equivalent is shown when you switch the toggle to Annual.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. Monthly plans have no long-term contract — cancel whenever you like.",
  },
  {
    q: "What's included in the free trial?",
    a: `${TRIAL.days} days and ${TRIAL.minutes} call minutes with every agent unlocked, the browser test console, the website chat widget and 50 texts.`,
  },
];

/* ------------------------------------------------------------------ contact form */

export const BUSINESS_TYPES = [
  { value: "clinic", label: "Clinic / doctors" },
  { value: "real_estate", label: "Real estate agency" },
  { value: "home_service", label: "Home services" },
  { value: "ecommerce", label: "E-commerce" },
  { value: "other", label: "Something else" },
] as const;

export const MONTHLY_CALLS = [
  { value: "<100", label: "Fewer than 100" },
  { value: "100–500", label: "100–500" },
  { value: "500–2,000", label: "500–2,000" },
  { value: "2,000+", label: "2,000+" },
] as const;

export const INTERESTS = [
  { value: "trial", label: `${TRIAL.days}-day free trial` },
  { value: "starter", label: "Starter plan" },
  { value: "growth", label: "Growth plan" },
  { value: "pro", label: "Pro plan" },
  { value: "enterprise", label: "Enterprise" },
  { value: "demo", label: "A live demo" },
] as const;
