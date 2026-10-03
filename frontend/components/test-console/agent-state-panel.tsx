"use client";

import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { outcomeLabel, t } from "@/lib/vertical";
import type { AgentState, VerticalSpec } from "@/services/api";

import type { SessionSetup } from "./types";

const GOOD = new Set(["confirmed", "booked", "rescheduled", "lead", "relay", "transfer"]);
const ATTENTION = new Set(["emergency", "unclear", "cancelled", "not_interested", "wrong_number", "auto_dropped"]);

function humanize(value: string): string {
  const text = value.replace(/[_.-]+/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "—";
}

function slotValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map((item) => slotValue(item)).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Live view of what the agent has understood so far in the current test. */
export function AgentStatePanel({
  state,
  setup,
  vertical,
  running,
}: {
  state: AgentState | null;
  setup: SessionSetup | null;
  vertical: VerticalSpec;
  running: boolean;
}) {
  const slots = Object.entries(state?.slots ?? {}).filter(([, value]) => value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && !value.length));
  const outcome = state?.outcome || "";
  const recordLabel = t(vertical.record_label, "record").toLowerCase();
  const recordId = state?.record_id || "";

  return (
    <Card aria-labelledby="agent-state-title">
      <CardHeader className="pb-3">
        <CardTitle id="agent-state-title" className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" aria-hidden />
          Agent state
          {running && (
            <span className="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-primary">
              <span className="status-dot inline-block h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
              Live
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!state ? (
          <p className="rounded-md border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
            Start a call or chat to see it live.
          </p>
        ) : (
          <div className="space-y-4 text-sm" aria-live="polite">
            <dl className="grid grid-cols-2 gap-3">
              <div className="min-w-0">
                <dt className="text-xs text-muted-foreground">Stage</dt>
                <dd className="mt-0.5 truncate font-medium" title={state.stage}>
                  {state.stage ? humanize(state.stage) : "—"}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs text-muted-foreground">Outcome</dt>
                <dd className="mt-0.5">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold",
                      GOOD.has(outcome)
                        ? "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300"
                        : ATTENTION.has(outcome)
                          ? "bg-[#ffedd5] text-[#9a3412] dark:bg-orange-500/15 dark:text-orange-300"
                          : "bg-secondary text-muted-foreground",
                    )}
                  >
                    {outcomeLabel(outcome)}
                  </span>
                </dd>
              </div>
            </dl>

            <div>
              <p className="text-xs font-semibold text-muted-foreground">Collected</p>
              {slots.length ? (
                <dl className="mt-1.5 divide-y divide-border rounded-md border border-border">
                  {slots.map(([key, value]) => (
                    <div key={key} className="grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-2 px-3 py-2">
                      <dt className="truncate text-xs text-muted-foreground" title={key}>
                        {humanize(key)}
                      </dt>
                      <dd className="break-words text-[13px] font-medium">{slotValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="mt-1.5 text-xs text-muted-foreground">Nothing yet.</p>
              )}
            </div>

            {recordId && (
              <Link
                href={`/orders/${encodeURIComponent(recordId)}`}
                className="flex items-center justify-between gap-2 rounded-md border border-tint-strong bg-accent px-3 py-2 text-sm font-medium text-accent-foreground transition hover:bg-tint"
              >
                {setup?.direction === "outbound" ? `View the ${recordLabel}` : `View the ${recordLabel} it created`}
                <ArrowRight className="h-4 w-4 shrink-0" aria-hidden />
              </Link>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
