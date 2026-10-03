import { cn } from "@/lib/utils";
import { outcomeLabel, statusLabel } from "@/lib/vertical";
import type { OrderStatus, SalesInquiryStatus, VerticalSpec } from "@/services/api";

/**
 * Admin-console chips. Kept local to the console (rather than reusing
 * components/status-badge) so the console's colour language stays stable.
 * Every chip carries a text label — colour is never the only signal.
 */
const PILL = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold";

export const TONES = {
  neutral: "bg-secondary text-muted-foreground",
  teal: "bg-accent text-accent-foreground",
  green: "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300",
  amber: "bg-[#fef3c7] text-[#92400e] dark:bg-amber-500/15 dark:text-amber-300",
  orange: "bg-[#ffedd5] text-[#9a3412] dark:bg-orange-500/15 dark:text-orange-300",
  red: "bg-[#fee2e2] text-[#991b1b] dark:bg-red-500/15 dark:text-red-300",
  blue: "bg-[#dbeafe] text-[#1d4ed8] dark:bg-blue-500/15 dark:text-blue-300",
  violet: "bg-[#ede9fe] text-[#5b21b6] dark:bg-violet-500/15 dark:text-violet-300",
  cyan: "bg-[#cffafe] text-[#155e75] dark:bg-cyan-500/15 dark:text-cyan-300",
} as const;

export type Tone = keyof typeof TONES;

export function Pill({ tone = "neutral", className, children, dot }: { tone?: Tone; className?: string; children: React.ReactNode; dot?: boolean }) {
  return (
    <span className={cn(PILL, TONES[tone], className)}>
      {dot && <span className="status-dot inline-block h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  return <Pill tone={active ? "green" : "neutral"}>{active ? "Active" : "Inactive"}</Pill>;
}

const STATUS_TONES: Record<OrderStatus, Tone> = {
  pending: "amber",
  calling: "blue",
  confirmed: "green",
  cancelled: "red",
  no_answer: "violet",
  needs_review: "orange",
};

/** A record status in the owning account's vocabulary ("Scheduled" for a clinic, "Pending" for a shop). */
export function RecordStatusBadge({ status, spec }: { status: OrderStatus | string; spec: VerticalSpec | null }) {
  return (
    <Pill tone={STATUS_TONES[status as OrderStatus] ?? "neutral"} dot={status === "calling"}>
      {statusLabel(spec, status)}
    </Pill>
  );
}

const OUTCOME_TONES: Record<string, Tone> = {
  confirmed: "green",
  booked: "green",
  lead: "green",
  rescheduled: "cyan",
  cancelled: "red",
  not_interested: "red",
  emergency: "red",
  wrong_number: "neutral",
  unclear: "orange",
  needs_review: "orange",
  transfer: "blue",
  relay: "blue",
  inquiry: "teal",
  no_answer: "violet",
  busy: "violet",
  failed: "violet",
  auto_dropped: "violet",
  diverted: "violet",
  voicemail: "violet",
};

export function OutcomePill({ outcome }: { outcome: string | null | undefined }) {
  if (!outcome) return <Pill tone="blue">{outcomeLabel(outcome)}</Pill>;
  return <Pill tone={OUTCOME_TONES[outcome] ?? "neutral"}>{outcomeLabel(outcome)}</Pill>;
}

export const INQUIRY_STATUSES: { value: SalesInquiryStatus; label: string; tone: Tone }[] = [
  { value: "new", label: "New", tone: "blue" },
  { value: "contacted", label: "Contacted", tone: "amber" },
  { value: "demo", label: "Demo booked", tone: "violet" },
  { value: "won", label: "Won", tone: "green" },
  { value: "lost", label: "Lost", tone: "neutral" },
];

export function InquiryStatusBadge({ status }: { status: SalesInquiryStatus | string }) {
  const entry = INQUIRY_STATUSES.find((item) => item.value === status);
  return <Pill tone={entry?.tone ?? "neutral"}>{entry?.label ?? status}</Pill>;
}
