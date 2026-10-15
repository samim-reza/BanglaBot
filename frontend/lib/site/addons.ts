/** Add-ons on the pricing page. Mirrors the catalog in backend/app/core/addons.py — change both together. */

export type AddonGroup = "channels" | "capacity" | "extras";

export type SiteAddon = {
  key: string;
  group: AddonGroup;
  name: string;
  price: string;
  summary: string;
  /** Short tag: where it's already included, or which plans it's for. */
  note?: string;
};

export const ADDON_GROUPS: { key: AddonGroup; label: string }[] = [
  { key: "channels", label: "Chat channels" },
  { key: "capacity", label: "More capacity" },
  { key: "extras", label: "Features & setup" },
];

export const ADDONS: SiteAddon[] = [
  {
    key: "web_chat",
    group: "channels",
    name: "Website chatbot",
    price: "$29 / mo",
    summary: "Your agent as a chat bubble on your site. 1,000 chats / mo.",
    note: "In the Chat agent plan",
  },
  { key: "whatsapp", group: "channels", name: "WhatsApp bot", price: "$49 / mo", summary: "Customers chat and book on WhatsApp. 300 chats / mo." },
  { key: "messenger", group: "channels", name: "Messenger bot", price: "$29 / mo", summary: "Answers your Facebook Page messages. 1,000 chats / mo." },
  { key: "instagram", group: "channels", name: "Instagram DM bot", price: "$29 / mo", summary: "Answers your Instagram direct messages. 1,000 chats / mo." },
  { key: "minutes", group: "capacity", name: "Extra 100 minutes", price: "$25 / mo", summary: "More call minutes every month.", note: "Voice plans" },
  { key: "sms", group: "capacity", name: "Extra 500 texts", price: "$10 / mo", summary: "More SMS confirmations and reminders." },
  { key: "number", group: "capacity", name: "Extra phone number", price: "$5 / mo", summary: "Another line for a branch or campaign.", note: "Voice plans" },
  {
    key: "google_calendar",
    group: "extras",
    name: "Two-way Google Calendar",
    price: "$9 / mo",
    summary: "Bookings sync both ways with Google.",
    note: "Included in Growth & Pro",
  },
  { key: "extra_language", group: "extras", name: "Extra language", price: "$19 / mo", summary: "Serve customers in a second language. Bangla today." },
  {
    key: "recording_retention",
    group: "extras",
    name: "12-month recordings",
    price: "$10 / mo",
    summary: "Keep call recordings for a year.",
    note: "Included in Pro",
  },
  { key: "setup", group: "extras", name: "Done-for-you setup", price: "$299 once", summary: "We load your catalog, script and number." },
];
