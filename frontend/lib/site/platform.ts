/** Platform features and the four setup steps, shared by every solution. */

import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  BookOpen,
  CalendarCheck,
  CalendarClock,
  CalendarSync,
  Globe,
  ListChecks,
  MessageSquare,
  MessageSquareText,
  PhoneCall,
  PhoneForwarded,
  Webhook,
  Zap,
} from "lucide-react";

export type Feature = { icon: LucideIcon; title: string; body: string };

export const FEATURES: Feature[] = [
  {
    icon: PhoneCall,
    title: "A real phone number, both ways",
    body: "Answers inbound calls and places outbound ones on a real number. Use ours, or forward your existing line.",
  },
  {
    icon: MessageSquare,
    title: "Website, WhatsApp, Messenger & Instagram",
    body: "The same agent, typed: a chat bubble on your site, your WhatsApp number, your Facebook Page or your Instagram DMs.",
  },
  {
    icon: BookOpen,
    title: "Answers only from your data",
    body: "Replies come from your catalog and knowledge base. If the answer isn't there, the agent says so.",
  },
  {
    icon: ListChecks,
    title: "Read-back before every booking",
    body: "Name, time, price and details are confirmed before anything is saved.",
  },
  {
    icon: CalendarCheck,
    title: "No double bookings",
    body: "Slots are checked against your schedule, capacity and calendar at the moment of booking, across every channel.",
  },
  {
    icon: MessageSquareText,
    title: "Text confirmations & reminders",
    body: "A text when they book, another if it changes, and a reminder before. Fewer no-shows.",
  },
  {
    icon: CalendarSync,
    title: "Syncs with your calendar",
    body: "Bookings land in Google Calendar instantly, or in Outlook and Apple via a private feed. Busy times are never offered.",
  },
  {
    icon: PhoneForwarded,
    title: "Live transfer to your team",
    body: "When a caller asks for a person, or the agent shouldn't handle it, the call goes straight to your staff.",
  },
  {
    icon: AudioLines,
    title: "Recordings, transcripts, outcomes",
    body: "Every call is recorded and transcribed, with a clear outcome: booked, rescheduled, cancelled, lead, follow-up.",
  },
  {
    icon: CalendarClock,
    title: "Bulk & scheduled campaigns",
    body: "Call a whole list at once or daily at a set time: reminders, confirmations, follow-ups.",
  },
  {
    icon: Webhook,
    title: "Webhooks into your systems",
    body: "Push every booking and outcome to your practice software, CRM or spreadsheet.",
  },
  {
    icon: Globe,
    title: "Your region, your language",
    body: "Currency, time zone, emergency number and accent per account. English today, Bangla available.",
  },
  {
    icon: Zap,
    title: "Fast, natural turns",
    body: "Scripted lines play from a voice cache and each turn takes one AI round-trip, so callers aren't left waiting.",
  },
];

export type Step = { title: string; body: string; points: string[] };

export const STEPS: Step[] = [
  {
    title: "Pick your business type",
    body: "Clinic, dental, vet, restaurant, salon, real estate, home services or e-commerce — or build your own. Your agent comes with its conversation flow, booking rules and safety rules built in.",
    points: ["Set once, when your account is created", "Region sets currency, time zone and emergency number"],
  },
  {
    title: "Add what you offer",
    body: "Your doctors, menu, services or listings, and when they're available. Then paste your FAQs, policies and prices into the knowledge base.",
    points: ["Days, hours, capacity and prices", "Edit any step or line of the call"],
  },
  {
    title: "Call it yourself",
    body: "Ring your agent's number from your phone and preview the website chat. Every call is transcribed, so you see exactly what it said and booked.",
    points: ["Works from any phone", "Tweak your greeting and knowledge, call again"],
  },
  {
    title: "Go live",
    body: "Point calls at your agent's number, and add chat to your site with one script tag. Bookings start landing in your portal.",
    points: ["Forward after hours or around the clock", "Reminder and follow-up calls on your schedule"],
  },
];
