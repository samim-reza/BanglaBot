/** Shapes of the public website's solution pages (one AgentSolution per business type). */

import type { LucideIcon } from "lucide-react";

/** Matches the backend's vertical keys (also used as ?type= on the contact form and ?vertical= on signup). */
export type AgentKey =
  | "clinic"
  | "dental"
  | "vet"
  | "restaurant"
  | "salon"
  | "real_estate"
  | "home_service"
  | "ecommerce"
  | "custom";

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
