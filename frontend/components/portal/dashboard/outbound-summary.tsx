"use client";

/** Outbound calls (order confirmations, reminder calls): how this period's calls ended, and every record by status now. */

import Link from "next/link";
import { CircleCheck, CircleX, Clock3, PhoneCall, PhoneMissed, PhoneOutgoing, RotateCcw, TriangleAlert, type LucideIcon } from "lucide-react";

import { StatTile } from "@/components/portal/dashboard/parts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { statusLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import type { OrderStatus, OutboundSummary } from "@/services/api";

const STATUS_TILES: { status: OrderStatus; icon: LucideIcon; accent: string; voice?: boolean }[] = [
  { status: "pending", icon: Clock3, accent: "text-[#92400e] dark:text-amber-300" },
  { status: "calling", icon: PhoneCall, accent: "text-[#1d4ed8] dark:text-blue-300", voice: true },
  { status: "confirmed", icon: CircleCheck, accent: "text-[#065f46] dark:text-emerald-300" },
  { status: "cancelled", icon: CircleX, accent: "text-destructive" },
  { status: "no_answer", icon: PhoneMissed, accent: "text-[#5b21b6] dark:text-violet-300", voice: true },
  { status: "needs_review", icon: TriangleAlert, accent: "text-[#9a3412] dark:text-orange-300" },
];

const TILE = "rounded-lg border border-border p-4 transition hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Every record by status right now — each tile opens the filtered list. */
export function StatusTiles({ stats, hasVoice }: { stats: OutboundSummary["statuses"]; hasVoice: boolean }) {
  const { vertical } = useWorkspace();
  const plural = t(vertical.record_label_plural, "Records");
  const tiles = STATUS_TILES.filter((tile) => hasVoice || !tile.voice);
  return (
    <section aria-label={`${plural} by status`} className={cn("grid grid-cols-2 gap-3 sm:grid-cols-4", hasVoice ? "xl:grid-cols-7" : "xl:grid-cols-5")}>
      {tiles.map(({ status, icon: Icon, accent }) => (
        <Link key={status} href={`/orders?status=${status}`} className={cn(TILE, "bg-card")}>
          <span className="flex items-center justify-between gap-2">
            <span className="truncate text-[13px] font-medium text-muted-foreground">{statusLabel(vertical, status)}</span>
            <Icon className={cn("h-4 w-4 shrink-0", accent)} aria-hidden="true" />
          </span>
          <span className="mt-2 block text-[26px] font-bold leading-tight tabular-nums">{(stats[status] ?? 0).toLocaleString("en-US")}</span>
        </Link>
      ))}
      <Link href="/orders" className={cn(TILE, "bg-surface xl:col-span-1", hasVoice ? "col-span-2" : "col-span-2 sm:col-span-4")}>
        <span className="text-[13px] font-medium text-muted-foreground">All {plural.toLowerCase()}</span>
        <span className="mt-2 block text-[26px] font-bold leading-tight tabular-nums">{(stats.total ?? 0).toLocaleString("en-US")}</span>
      </Link>
    </section>
  );
}

export function OutboundCalls({ outbound, title, hasVoice }: { outbound: OutboundSummary; title: string; hasVoice: boolean }) {
  const { vertical } = useWorkspace();
  const label = t(vertical.outbound_label, "Outbound call");
  const n = (value: number) => value.toLocaleString("en-US");
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>
          {label}s {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasVoice && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <StatTile label="Calls placed" value={n(outbound.calls)} icon={PhoneOutgoing} />
            <StatTile label="Confirmed" value={n(outbound.confirmed)} icon={CircleCheck} accent="text-[#065f46] dark:text-emerald-300" />
            <StatTile label="Cancelled" value={n(outbound.cancelled)} icon={CircleX} accent="text-destructive" />
            <StatTile label="No answer" value={n(outbound.no_answer)} icon={PhoneMissed} accent="text-[#5b21b6] dark:text-violet-300" />
            <StatTile label="Rescheduled" value={n(outbound.rescheduled)} icon={RotateCcw} />
            <StatTile label="Needs review" value={n(outbound.needs_review)} icon={TriangleAlert} accent="text-[#9a3412] dark:text-orange-300" href="/orders?status=needs_review" />
          </div>
        )}
        <StatusTiles stats={outbound.statuses} hasVoice={hasVoice} />
      </CardContent>
    </Card>
  );
}
