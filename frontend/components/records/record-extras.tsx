"use client";

/** What the call flow added to a record: intake answers (`details.intake`), visit type, consent time. */

import { humanize } from "@/lib/format";
import { formatInZone } from "@/lib/vertical";
import type { Order } from "@/services/api";

import { KeyValueList, looseValue, type KeyValueEntry } from "./key-values";

/** `details` keys rendered here (or by the payment card), not in the generic list. */
export const FLOW_DETAIL_KEYS = new Set(["intake", "visit_mode", "consent", "payment"]);

const VISIT_MODES: Record<string, string> = { in_person: "In person", online: "Online", phone: "By phone", video: "Video call" };

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

/** "f_shoe_size" (custom question) → "Shoe size". */
function answerLabel(key: string): string {
  return humanize(key.startsWith("f_") ? key.slice(2) : key);
}

export function recordExtraEntries(order: Order, timezone?: string): KeyValueEntry[] {
  const details = order.details ?? {};
  const entries: KeyValueEntry[] = Object.entries(record(details.intake))
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => [answerLabel(key), looseValue(value)]);
  if (typeof details.visit_mode === "string" && details.visit_mode) {
    entries.push(["Visit", VISIT_MODES[details.visit_mode] ?? humanize(details.visit_mode)]);
  }
  const consent = record(details.consent);
  if (typeof consent.at === "string" && consent.at) entries.push(["Agreed to terms", formatInZone(consent.at, timezone)]);
  return entries;
}

export function RecordExtras({ order, timezone }: { order: Order; timezone?: string }) {
  const entries = recordExtraEntries(order, timezone);
  if (!entries.length) return null;
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">From the call</p>
      <KeyValueList entries={entries} />
    </div>
  );
}
