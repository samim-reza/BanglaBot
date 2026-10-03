import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { cn } from "@/lib/utils";

/** A KPI tile: label, value and an optional hint. With `href` the whole tile links to the filtered view. */
export function KpiTile({
  label,
  value,
  hint,
  icon: Icon,
  href,
  emphasis,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  href?: string;
  /** Draws the eye (e.g. records waiting for a person). */
  emphasis?: boolean;
}) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-muted-foreground">{label}</span>
        {href ? (
          <ArrowUpRight className="h-4 w-4 text-muted-foreground transition-colors group-hover:text-primary" aria-hidden="true" />
        ) : (
          Icon && <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        )}
      </div>
      <p className={cn("mt-2 text-[26px] font-semibold leading-tight", emphasis && "text-[#9a3412] dark:text-orange-300")}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </>
  );
  const frame = cn(
    "block rounded-lg border border-border bg-card p-4 text-card-foreground",
    emphasis && "border-[#fdba74] dark:border-orange-500/40",
  );
  if (href) {
    return (
      <Link
        href={href}
        className={cn(frame, "group transition-colors hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
      >
        {body}
      </Link>
    );
  }
  return <div className={frame}>{body}</div>;
}

/**
 * A ratio against a limit. The fill carries severity (teal → amber at 80% →
 * red past the limit); the track is a light step of the same teal.
 */
export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const ratio = max > 0 ? value / max : 0;
  const pct = Math.max(0, Math.min(100, ratio * 100));
  const fill = ratio > 1 ? "bg-destructive" : ratio >= 0.8 ? "bg-[#d97706] dark:bg-amber-400" : "bg-primary";
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      aria-valuetext={`${Math.round(ratio * 100)}%`}
      className="h-2 w-full overflow-hidden rounded-full bg-tint"
    >
      <div className={cn("h-full rounded-full transition-[width]", fill)} style={{ width: `${pct}%` }} />
    </div>
  );
}
