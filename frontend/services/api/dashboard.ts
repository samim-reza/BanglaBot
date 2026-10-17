/** The owner dashboard's summary: what the agent did today / this week / last 30 days. */

import { request } from "./client";
import type { OrderStats } from "./types";

export type DashboardRange = "today" | "7d" | "30d";

/** Calls the business placed (confirmations, reminders) in the period and how they ended. */
export type OutboundSummary = {
  calls: number;
  confirmed: number;
  /** Cancelled or not interested. */
  cancelled: number;
  no_answer: number;
  rescheduled: number;
  needs_review: number;
  /** Every record by status right now (the status tiles). */
  statuses: OrderStats;
};

export type DashboardSummary = {
  range: DashboardRange;
  start: string;
  end: string;
  timezone: string;
  currency: string;
  /** False for outbound-first accounts (order confirmations). */
  inbound_first: boolean;
  calls_answered: number;
  chats_handled: number;
  /** Bookings / orders the agent made (not cancelled) and their total. */
  bookings: number;
  bookings_value: number;
  messages_leads: number;
  /** Answered calls outside working hours. */
  after_hours: number;
  /** False = no schedule set, so "after hours" means outside weekdays 9–5. */
  hours_known: boolean;
  transfers_urgent: number;
  avg_call_secs: number;
  minutes_used: number;
  /** Only for accounts that place outbound calls. */
  outbound: OutboundSummary | null;
};

export const dashboardApi = {
  summary: (range: DashboardRange = "7d") =>
    request<DashboardSummary>(`/api/dashboard/summary?range=${range}`, { auth: "merchant" }),
};
