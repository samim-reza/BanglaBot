/** Shared facts for the Privacy Policy and Terms of Service (lib/site/legal-privacy.ts, legal-terms.ts).
 *
 * OWNER: the values marked "OWNER" are business decisions — review them before relying on the pages.
 * Retention numbers mirror backend/app/core/plans.py + addons.py (12-month recordings on Pro / add-on).
 * In legal copy, `[label](/path)` renders as a link (see components/site/legal-page.tsx).
 */

import { BRAND } from "@/lib/brand";

/** A paragraph, a bulleted list, a list of labelled items, or a small table. */
export type LegalBlock =
  | string
  | { list: string[] }
  | { terms: [label: string, detail: string][] }
  | { table: { head: string[]; rows: string[][] } };

export type LegalSection = { id: string; title: string; blocks: LegalBlock[] };

export type LegalDoc = {
  title: string;
  /** Meta description. */
  description: string;
  updated: string;
  /** One or two sentences under the title. */
  summary: string;
  sections: LegalSection[];
};

export const LEGAL = {
  /** OWNER: the registered company name that contracts with customers (e.g. "Callisa, Inc."). */
  entity: BRAND.name,
  /** OWNER: governing law and courts for the Terms. Delaware is a neutral placeholder. */
  governingLaw: "the State of Delaware, USA",
  courts: "the state and federal courts located in Delaware, USA",
  /** OWNER: where the main servers and database run today (Render + Supabase, Singapore). */
  hostingRegion: "Singapore",
  updated: "October 18, 2026",
} as const;

export const RETENTION = {
  /** OWNER: default recording retention. Make sure recordings are actually deleted on this schedule. */
  recordingDays: 30,
  /** Pro plan or the "12-month recordings" add-on. */
  extendedRecordingMonths: 12,
  /** OWNER: how long after an account closes its data is deleted. */
  closedAccountDays: 90,
} as const;

/** How to reach us, as legal copy: the public email when NEXT_PUBLIC_CONTACT_EMAIL is set, else the form. */
export const CONTACT_US = BRAND.contactEmail
  ? `email [${BRAND.contactEmail}](mailto:${BRAND.contactEmail}) or use our [contact form](/contact)`
  : "use our [contact form](/contact)";

/** The text-message program, worded for US carrier (A2P 10DLC) review. Used by both pages. */
export const SMS_PROGRAM = {
  name: `${BRAND.name} booking notifications`,
  messages: "Booking confirmations, changes and cancellations, appointment and order reminders, and payment links",
  sharing:
    "No mobile information will be shared with third parties or affiliates for marketing or promotional purposes. Text-message opt-in data and consent will not be shared with any third parties.",
} as const;

export function smsTermsBlocks(): LegalBlock[] {
  return [
    `Program name: ${SMS_PROGRAM.name}. Businesses that use ${BRAND.name} send text messages to their own customers about something the customer asked for, such as a booking or an order. You receive texts only after you give a business your mobile number for that purpose, for example during a call or chat.`,
    {
      terms: [
        ["What we send", `${SMS_PROGRAM.messages}. No marketing messages.`],
        ["How often", "Message frequency varies with your bookings and orders."],
        ["Cost", "Msg & data rates may apply."],
        ["Opt out", "Reply STOP to any message to stop texts from that number. Reply START to receive them again."],
        ["Help", `Reply HELP for help, or ${CONTACT_US}.`],
      ],
    },
    "Carriers are not liable for delayed or undelivered messages.",
    SMS_PROGRAM.sharing,
  ];
}

/** Service providers that process personal information for us. OWNER: keep this list current. */
export const SUBPROCESSORS: { name: string; purpose: string; location: string }[] = [
  { name: "Telnyx", purpose: "Phone numbers, call connection and recording, text messages", location: "USA" },
  { name: "Twilio", purpose: "WhatsApp messaging", location: "USA" },
  { name: "Deepgram", purpose: "Speech recognition and text-to-speech", location: "USA" },
  { name: "OpenAI", purpose: "Speech recognition and AI language models", location: "USA" },
  { name: "Groq", purpose: "AI language models and speech recognition", location: "USA" },
  { name: "Google", purpose: "Gemini AI models and text-to-speech; Google Calendar sync (when connected)", location: "USA" },
  { name: "Microsoft Azure", purpose: "Text-to-speech", location: "Singapore, USA" },
  { name: "Supabase", purpose: "Database and file storage", location: LEGAL.hostingRegion },
  { name: "Render", purpose: "Application hosting", location: LEGAL.hostingRegion },
  { name: "Vercel", purpose: "Website and portal hosting", location: "Global edge network" },
  { name: "Meta", purpose: "WhatsApp, Messenger and Instagram messaging (when connected)", location: "USA" },
  { name: "Stripe", purpose: "Payments and billing", location: "USA" },
];
