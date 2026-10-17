"use client";

/** The dashboard's "This month" card: plan usage against its allowances. */

import { UsageMeter } from "@/components/portal/kit";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { money } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";

const fmt = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 1 });

export function MonthCard({ hasVoice, hasChat }: { hasVoice: boolean; hasChat: boolean }) {
  const { usage } = useWorkspace();
  const limits = usage.limits;
  const minutesLimit = limits.minutes;
  const minutesNote =
    minutesLimit === null || minutesLimit <= 0
      ? null
      : usage.overage_minutes > 0
        ? `${fmt(usage.overage_minutes)} min over${usage.plan.overage_per_minute ? ` · ${money(usage.plan.overage_per_minute, "USD")}/min` : ""}`
        : `${fmt(usage.minutes_left ?? Math.max(0, minutesLimit - usage.minutes))} min left`;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div className="space-y-1">
          <CardTitle>This month</CardTitle>
          <CardDescription>Since {formatDate(usage.period_start)}</CardDescription>
        </div>
        <span className="rounded-full bg-accent px-2.5 py-0.5 text-[12px] font-semibold text-accent-foreground">{usage.plan.name}</span>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasVoice && (
          <div>
            <UsageMeter label="Call minutes" used={usage.minutes} included={limits.minutes} unit="min" />
            {minutesNote && <p className="mt-1.5 text-xs text-muted-foreground">{minutesNote}</p>}
          </div>
        )}
        {hasChat && <UsageMeter label="Chats" used={usage.chats} included={limits.chats} unit="chats" />}
        <UsageMeter label="Texts" used={usage.sms ?? 0} included={limits.sms} unit="texts" />
        {hasVoice && (
          <dl className="flex items-baseline justify-between gap-3 border-t border-border pt-4 text-sm">
            <dt className="text-muted-foreground">Calls</dt>
            <dd className="text-lg font-semibold tabular-nums">{usage.calls.toLocaleString("en-US")}</dd>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
