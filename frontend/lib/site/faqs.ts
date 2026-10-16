/** FAQs for the home and pricing pages. */

import { TRIAL } from "./pricing";

export type Faq = { q: string; a: string };

export const HOME_FAQS: Faq[] = [
  {
    q: "Where does the agent get its answers?",
    a: "Only from what you give it: your catalog and your knowledge base. If something isn't covered, it says so, takes a message or transfers the call. It doesn't make things up.",
  },
  {
    q: "Can I keep my existing phone number?",
    a: "Yes. Forward your line to your agent's number around the clock, after hours only, or when your team doesn't pick up.",
  },
  {
    q: "Can it answer chats as well as calls?",
    a: "Yes. Add the website chatbot ($29/mo), WhatsApp ($49/mo), Messenger ($29/mo) or Instagram ($29/mo) to any voice plan. Only need website chat? The Chat agent plan is $29 a month.",
  },
  {
    q: "Where do bookings go?",
    a: "Straight into your records in the portal, with double-booking protection. On Growth and Pro, webhooks also push them into your own systems.",
  },
  {
    q: "What happens when a caller needs a real person?",
    a: "On Growth and Pro the agent transfers the call live to your team. Otherwise it takes the details and flags the call for follow-up.",
  },
  {
    q: "Which languages does it speak?",
    a: "English, with the accent set per account (US, UK, Australian, Indian and more).",
  },
  {
    q: "How much work is setup?",
    a: "Add your doctors, menu, services or listings, paste your FAQs and call your number to try it. Or let us do it: done-for-you setup is $299 once.",
  },
  {
    q: "Is there a free trial?",
    a: `Yes: ${TRIAL.days} days with ${TRIAL.minutes} call minutes, ${TRIAL.texts} texts and every channel switched on.`,
  },
];

export const PRICING_FAQS: Faq[] = [
  {
    q: "Do voice plans include website chat?",
    a: "No. Voice plans cover your phone line. Add the website chatbot for $29 a month (1,000 chats), or choose the Chat agent plan if chat is all you need.",
  },
  {
    q: "What counts as a call minute?",
    a: "Connected call time: the time a caller is on the line with your agent. Inbound and outbound minutes come from the same pool.",
  },
  {
    q: "What happens if I go over my minutes?",
    a: "Your agent keeps answering. Extra minutes are billed at your plan's rate: $0.30 on Starter, $0.22 on Growth, $0.16 on Pro. On Starter, a 100-minute add-on ($25/mo) works out cheaper.",
  },
  {
    q: "What counts as a chat?",
    a: "A conversation in which the customer sent at least one message, on your website, WhatsApp, Messenger or Instagram. Chats on every channel share one monthly allowance.",
  },
  {
    q: "What do WhatsApp, Messenger and Instagram cost?",
    a: "The WhatsApp bot is $49 a month with 300 chats; the Messenger and Instagram bots are $29 each with 1,000 chats. Any WhatsApp fees Meta charges are passed through at cost.",
  },
  {
    q: "Are text messages included?",
    a: "Yes. SMS confirmations and reminders: 100 a month on Chat agent and Starter, 500 on Growth, 2,000 on Pro. Extra texts are $10 per 500 a month. A long message can use more than one text.",
  },
  {
    q: "How do add-ons work?",
    a: "Request one in your portal and we switch it on for your account. Monthly add-ons are billed with your plan, and you can drop them anytime.",
  },
  {
    q: "Which calendars do you work with?",
    a: "Two-way Google Calendar is included in Growth and Pro, and $9 a month on other plans. Outlook, Apple and other calendars subscribe to your private booking feed and share busy times through an iCal link.",
  },
  {
    q: "Do international calls cost more?",
    a: "Outbound calls on expensive international routes can use more than one included minute per minute. If you call abroad often, ask sales about volume rates.",
  },
  {
    q: "Can I cancel, or pay yearly?",
    a: "Monthly plans have no contract; cancel anytime. Pay yearly and you get 12 months for the price of 10.",
  },
  {
    q: "What's included in the free trial?",
    a: `${TRIAL.days} days, ${TRIAL.minutes} call minutes and ${TRIAL.texts} texts, with every channel and feature switched on.`,
  },
];
