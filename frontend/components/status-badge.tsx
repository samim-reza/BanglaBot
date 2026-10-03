import { cn } from "@/lib/utils";
import { channelLabel, outcomeLabel, statusLabel } from "@/lib/vertical";
import type { OrderStatus, VerticalSpec } from "@/services/api";

/** Pill badge base shared by every status/outcome chip (ported from the original theme). */
export const BADGE_BASE = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold";

const AMBER = "bg-[#fef3c7] text-[#92400e] dark:bg-amber-500/15 dark:text-amber-300";
const BLUE = "bg-[#dbeafe] text-[#1d4ed8] dark:bg-blue-500/15 dark:text-blue-300";
const GREEN = "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300";
const RED = "bg-[#fee2e2] text-[#991b1b] dark:bg-red-500/15 dark:text-red-300";
const VIOLET = "bg-[#ede9fe] text-[#5b21b6] dark:bg-violet-500/15 dark:text-violet-300";
const ORANGE = "bg-[#ffedd5] text-[#9a3412] dark:bg-orange-500/15 dark:text-orange-300";
const CYAN = "bg-[#cffafe] text-[#155e75] dark:bg-cyan-500/15 dark:text-cyan-300";
const GREY = "bg-[#f3f4f6] text-[#6b7280] dark:bg-secondary dark:text-muted-foreground";
const NEUTRAL = "bg-secondary text-muted-foreground";

/** Status → colour pair from the original theme, with a dimmed dark-mode variant. */
export const STATUS_STYLES: Record<string, string> = {
  pending: AMBER,
  calling: BLUE,
  confirmed: GREEN,
  cancelled: RED,
  no_answer: VIOLET,
  diverted: VIOLET,
  voicemail: VIOLET,
  needs_review: ORANGE,
  rescheduled: CYAN,
  active: GREEN,
  inactive: GREY,
};

/**
 * A record's status. Pass the account's vertical so the label reads the way the
 * business talks ("Scheduled", "Visit booked"); without it the generic label is used.
 */
export function OrderStatusBadge({
  status,
  spec,
  label,
  className,
}: {
  status: OrderStatus | string;
  spec?: VerticalSpec | null;
  label?: string;
  className?: string;
}) {
  const style = STATUS_STYLES[status] ?? NEUTRAL;
  const live = status === "calling";
  return (
    <span className={cn(BADGE_BASE, style, className)}>
      {live && <span className="status-dot inline-block h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {label ?? statusLabel(spec ?? null, status)}
    </span>
  );
}

/** Alias with the vertical-neutral name. */
export const RecordStatusBadge = OrderStatusBadge;

function outcomeStyle(outcome: string | null | undefined): string {
  switch (outcome) {
    case "confirmed":
    case "booked":
      return GREEN;
    case "rescheduled":
      return CYAN;
    case "lead":
      return BLUE;
    case "cancelled":
    case "not_interested":
    case "emergency":
      return RED;
    case "no_answer":
    case "busy":
    case "failed":
    case "auto_dropped":
    case "diverted":
    case "voicemail":
      return VIOLET;
    case "needs_review":
    case "unclear":
    case "wrong_number":
    case "transfer":
    case "relay":
      return ORANGE;
    default:
      return NEUTRAL;
  }
}

/** Line results (Twilio call status) for a call that ended before the agent recorded an outcome. */
const LINE_RESULTS: Record<string, string> = {
  "no-answer": "No answer",
  busy: "Busy",
  failed: "Call failed",
  canceled: "Not connected",
  completed: "No outcome",
};

/**
 * The agent's outcome for a call or chat. Pass `callStatus` so a call that never
 * reached the agent reads "No answer" / "Busy" instead of "In progress".
 */
export function OutcomeBadge({
  outcome,
  callStatus,
  className,
}: {
  outcome: string | null | undefined;
  callStatus?: string | null;
  className?: string;
}) {
  if (!outcome && callStatus && LINE_RESULTS[callStatus]) {
    const style = callStatus === "completed" ? NEUTRAL : VIOLET;
    return <span className={cn(BADGE_BASE, style, className)}>{LINE_RESULTS[callStatus]}</span>;
  }
  return <span className={cn(BADGE_BASE, outcomeStyle(outcome), className)}>{outcomeLabel(outcome)}</span>;
}

const SOURCE_LABELS: Record<string, string> = {
  manual: "Added by you",
  inbound_call: "Inbound call",
  outbound_call: "Outbound call",
  website_chat: "Website chat",
  widget: "Website chat",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
  test: "Test",
  import: "Import",
};

export function sourceLabel(source: string | null | undefined): string {
  if (!source) return "—";
  return SOURCE_LABELS[source] ?? source.replace(/_/g, " ");
}

/** Where a record came from (manual entry, a call, website chat, WhatsApp, Messenger, a test). */
export function SourceBadge({ source, className }: { source: string | null | undefined; className?: string }) {
  const style = source === "test" ? AMBER : source === "manual" || !source ? NEUTRAL : "bg-accent text-accent-foreground";
  return <span className={cn(BADGE_BASE, "font-medium", style, className)}>{sourceLabel(source)}</span>;
}

const CHANNEL_STYLES: Record<string, string> = {
  web: AMBER,
  chat: AMBER,
  widget: CYAN,
  whatsapp: GREEN,
  messenger: BLUE,
};

/** Call / chat channel chip (inbound, outbound, website chat, WhatsApp, Messenger, browser test, chat test). */
export function ChannelBadge({ direction, className }: { direction: string | null | undefined; className?: string }) {
  const style = CHANNEL_STYLES[direction ?? ""] ?? "bg-accent text-accent-foreground";
  return <span className={cn(BADGE_BASE, "font-medium", style, className)}>{channelLabel(direction)}</span>;
}
