/** Test the agent from the portal: browser voice call ticket, or a typed chat. */

import { request } from "./client";
import type { ChatReply, ChatStart, TestCallInput, TestCallTicket } from "./types";

export const agentApi = {
  /** Ticket for a browser voice call (see lib/web-call.ts). */
  testCall: (values: TestCallInput) =>
    request<TestCallTicket>("/api/agent/test-call", { method: "POST", auth: "merchant", body: JSON.stringify(values) }),
  startChat: (values: TestCallInput) =>
    request<ChatStart>("/api/agent/chat", { method: "POST", auth: "merchant", body: JSON.stringify(values) }),
  say: (sessionId: string, text: string) =>
    request<ChatReply>(`/api/agent/chat/${encodeURIComponent(sessionId)}`, {
      method: "POST",
      auth: "merchant",
      body: JSON.stringify({ text }),
    }),
  endChat: (sessionId: string) =>
    request<ChatReply>(`/api/agent/chat/${encodeURIComponent(sessionId)}/end`, { method: "POST", auth: "merchant" }),
};
