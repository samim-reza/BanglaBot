/** Trial, plans and price helpers. Numbers mirror backend/app/core/plans.py — change both together. */

export const TRIAL = { days: 14, minutes: 50, texts: 50 } as const;

export type SitePlan = {
  key: "chat" | "starter" | "growth" | "pro";
  /** Which product the plan is: the website chat agent or the voice agent. */
  product: "chat" | "voice";
  name: string;
  price: number;
  minutes: number;
  chats: number;
  /** Texts (SMS confirmations + reminders) included each month. */
  sms: number;
  numbers: number;
  /** Per extra call minute; 0 for the chat plan. */
  overage: number;
  tagline: string;
  features: string[];
  highlight: boolean;
};

export const PLANS: SitePlan[] = [
  {
    key: "chat",
    product: "chat",
    name: "Chat agent",
    price: 29,
    minutes: 0,
    chats: 1000,
    sms: 100,
    numbers: 0,
    overage: 0,
    tagline: "A chatbot for your website. No phone line.",
    features: [
      "Website chatbot (one script tag)",
      "1,000 chats / month",
      "100 texts / month",
      "Bookings, leads and transcripts",
      "Calendar feed (Google, Outlook, Apple)",
    ],
    highlight: false,
  },
  {
    key: "starter",
    product: "voice",
    name: "Starter",
    price: 49,
    minutes: 150,
    chats: 0,
    sms: 100,
    numbers: 1,
    overage: 0.3,
    tagline: "One number. Never miss a call.",
    features: [
      "1 phone number",
      "150 call minutes / month",
      "100 texts / month",
      "Bookings, leads and call recordings",
      "Calendar feed (Google, Outlook, Apple)",
      "Email support",
    ],
    highlight: false,
  },
  {
    key: "growth",
    product: "voice",
    name: "Growth",
    price: 149,
    minutes: 600,
    chats: 0,
    sms: 500,
    numbers: 2,
    overage: 0.22,
    tagline: "For busy front desks.",
    features: [
      "Everything in Starter",
      "2 phone numbers",
      "600 call minutes / month",
      "500 texts / month",
      "Reminder & confirmation calls",
      "Two-way Google Calendar",
      "Webhooks + live transfer",
    ],
    highlight: true,
  },
  {
    key: "pro",
    product: "voice",
    name: "Pro",
    price: 349,
    minutes: 1800,
    chats: 0,
    sms: 2000,
    numbers: 3,
    overage: 0.16,
    tagline: "For multi-location teams.",
    features: [
      "Everything in Growth",
      "3 phone numbers",
      "1,800 call minutes / month",
      "2,000 texts / month",
      "Bulk & scheduled campaigns",
      "12-month recordings",
      "Priority support",
    ],
    highlight: false,
  },
];

/** The voice agent plans (phone minutes) — what the ROI calculator compares against. */
export const VOICE_PLANS = PLANS.filter((plan) => plan.product === "voice");

export const ENTERPRISE = {
  name: "Enterprise",
  priceFrom: 999,
  tagline: "Custom volume, locations, SLAs and integrations.",
  features: ["Every channel and feature", "Volume minutes from $0.10", "Custom integrations & SSO", "Dedicated success manager"],
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
