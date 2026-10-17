"use client";

/** "Your agent this week": what the agent did — answered, booked, after hours — for today / 7 / 30 days. */

import { CalendarCheck, Clock3, Inbox, MessageSquare, MoonStar, PhoneForwarded, PhoneIncoming, Timer } from "lucide-react";

import { SkeletonTiles, StatTile } from "@/components/portal/dashboard/parts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { money, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import type { DashboardRange, DashboardSummary } from "@/services/api";

const RANGES: { value: DashboardRange; label: string; title: string }[] = [
  { value: "today", label: "Today", title: "today" },
  { value: "7d", label: "7 days", title: "this week" },
  { value: "30d", label: "30 days", title: "last 30 days" },
];

const count = (value: number) => value.toLocaleString("en-US");

/** 127 → "2:07". */
function duration(seconds: number): string {
  if (!seconds) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function RangeToggle({ value, onChange, disabled }: { value: DashboardRange; onChange: (value: DashboardRange) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Period" className="inline-flex rounded-md border border-input bg-card p-0.5">
      {RANGES.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "h-8 rounded px-3 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function AgentSummary({
  summary,
  range,
  onRange,
  hasVoice,
  hasChat,
}: {
  summary: DashboardSummary | null;
  range: DashboardRange;
  onRange: (value: DashboardRange) => void;
  hasVoice: boolean;
  hasChat: boolean;
}) {
  const { vertical } = useWorkspace();
  const plural = t(vertical.record_label_plural, "Bookings");
  const title = RANGES.find((option) => option.value === range)?.title ?? "";
  const loading = !summary || summary.range !== range;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle>Your agent {title}</CardTitle>
        <RangeToggle value={range} onChange={onRange} />
      </CardHeader>
      <CardContent>
        {loading || !summary ? (
          <SkeletonTiles count={hasVoice ? 8 : 4} />
        ) : (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-live="polite">
            {hasVoice && <StatTile label="Calls answered" value={count(summary.calls_answered)} icon={PhoneIncoming} href="/calls" />}
            {hasChat && <StatTile label="Chats handled" value={count(summary.chats_handled)} icon={MessageSquare} href="/calls" />}
            <StatTile
              label={`${plural} made`}
              value={count(summary.bookings)}
              icon={CalendarCheck}
              note={summary.bookings_value > 0 ? money(summary.bookings_value, summary.currency) : undefined}
              href="/orders"
            />
            <StatTile label="Messages & leads" value={count(summary.messages_leads)} icon={Inbox} href="/orders" />
            {hasVoice && (
              <StatTile
                label="After hours"
                value={count(summary.after_hours)}
                icon={MoonStar}
                note={summary.hours_known ? "Outside your hours" : "Outside 9–5"}
              />
            )}
            <StatTile label="Transfers & urgent" value={count(summary.transfers_urgent)} icon={PhoneForwarded} href="/calls" />
            {hasVoice && <StatTile label="Avg call" value={duration(summary.avg_call_secs)} icon={Timer} />}
            {hasVoice && (
              <StatTile label="Minutes used" value={summary.minutes_used.toLocaleString("en-US", { maximumFractionDigits: 1 })} icon={Clock3} />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
