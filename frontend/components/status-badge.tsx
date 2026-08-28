import { cn } from "@/lib/utils";
import { humanize } from "@/lib/format";
import type { OrderStatus } from "@/services/api";

/** Pill badge base shared by every status/outcome chip (ported from the original theme). */
export const BADGE_BASE = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold";

/** Status → colour pair from the original theme, with a dimmed dark-mode variant. */
export const STATUS_STYLES: Record<string, string> = {
  pending: "bg-[#fef3c7] text-[#92400e] dark:bg-amber-500/15 dark:text-amber-300",
  calling: "bg-[#dbeafe] text-[#1d4ed8] dark:bg-blue-500/15 dark:text-blue-300",
  confirmed: "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300",
  cancelled: "bg-[#fee2e2] text-[#991b1b] dark:bg-red-500/15 dark:text-red-300",
  no_answer: "bg-[#ede9fe] text-[#5b21b6] dark:bg-violet-500/15 dark:text-violet-300",
  diverted: "bg-[#ede9fe] text-[#5b21b6] dark:bg-violet-500/15 dark:text-violet-300",
  voicemail: "bg-[#ede9fe] text-[#5b21b6] dark:bg-violet-500/15 dark:text-violet-300",
  needs_review: "bg-[#ffedd5] text-[#9a3412] dark:bg-orange-500/15 dark:text-orange-300",
  rescheduled: "bg-[#cffafe] text-[#155e75] dark:bg-cyan-500/15 dark:text-cyan-300",
  active: "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300",
  inactive: "bg-[#f3f4f6] text-[#6b7280] dark:bg-secondary dark:text-muted-foreground",
};

const NEUTRAL = "bg-secondary text-muted-foreground";

export function OrderStatusBadge({ status, className }: { status: OrderStatus | string; className?: string }) {
  const style = STATUS_STYLES[status] ?? NEUTRAL;
  const live = status === "calling";
  return (
    <span className={cn(BADGE_BASE, style, className)}>
      {live && <span className="status-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />}
      {humanize(status)}
    </span>
  );
}

function outcomeStyle(outcome: string | null | undefined): string {
  switch (outcome) {
    case "confirmed":
    case "cancelled":
    case "no_answer":
    case "needs_review":
      return STATUS_STYLES[outcome];
    case "busy":
    case "failed":
    case "auto_dropped":
    case "diverted":
    case "voicemail":
      return STATUS_STYLES.no_answer;
    default:
      return NEUTRAL;
  }
}

export function OutcomeBadge({ outcome, className }: { outcome: string | null | undefined; className?: string }) {
  return <span className={cn(BADGE_BASE, outcomeStyle(outcome), className)}>{humanize(outcome ?? "in progress")}</span>;
}
