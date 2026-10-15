import { cn } from "@/lib/utils";

/** A neutral ratio (e.g. a cache hit rate): teal fill on a lighter teal track, no severity colours. */
export function RatioBar({ ratio, label, className }: { ratio: number; label: string; className?: string }) {
  const pct = Math.max(0, Math.min(100, ratio * 100));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-valuetext={`${Math.round(pct)}%`}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-tint", className)}
    >
      <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Label + value pairs in a compact grid. */
export function Facts({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="truncate font-medium tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
