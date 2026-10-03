import type { AgentState, Direction, VerticalKey } from "@/services/api";

export type ConsoleMode = "voice" | "chat";

/** One line of a test conversation. */
export type Line = { id: number; role: "agent" | "caller" | "system"; text: string };

/** What a test session was started with (shown next to it, and used for the next one). */
export type SessionSetup = {
  direction: Direction;
  /** Outbound only: the record the agent calls about. */
  recordId: string;
  recordName: string;
  /** Inbound only: pretend caller ID. */
  callerNumber: string;
};

export type SessionView = { setup: SessionSetup | null; state: AgentState | null };

let sequence = 0;
export function nextLineId(): number {
  sequence += 1;
  return sequence;
}

const INBOUND_SAMPLES: Record<VerticalKey, string[]> = {
  clinic: ["I'd like to see a pediatrician tomorrow morning", "What are your opening hours?", "I need to cancel my appointment"],
  real_estate: ["I'm looking to buy a 3-bedroom house under 500k", "Do you have apartments for rent downtown?", "I want to sell my land"],
  home_service: ["My AC is leaking water", "How much is a plumber call-out?", "I smell gas in the kitchen"],
  ecommerce: ["Where is my order?", "I want to return something"],
};

const OUTBOUND_SAMPLES: Record<VerticalKey, string[]> = {
  ecommerce: ["Yes, that's my order", "Please cancel it", "Can you deliver it to a different address?"],
  clinic: ["Yes, I'll be there", "Can I move it to Thursday?", "Please cancel it"],
  real_estate: ["Yes, I'm still looking", "Can I see it on Saturday morning?", "I've already found a place, thanks"],
  home_service: ["Yes, that time works", "Can you come in the afternoon instead?", "I don't need the visit anymore"],
};

export function samplesFor(vertical: VerticalKey, direction: Direction): string[] {
  const table = direction === "outbound" ? OUTBOUND_SAMPLES : INBOUND_SAMPLES;
  return table[vertical] ?? [];
}
