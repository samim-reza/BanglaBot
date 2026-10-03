import { cn } from "@/lib/utils";

/** Placeholder rows while a list loads (announced once to screen readers). */
export function LoadingRows({ label, rows = 5, className }: { label: string; rows?: number; className?: string }) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-4", className)} role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="space-y-3" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="flex items-center gap-4">
            <div className="h-4 w-1/4 animate-pulse rounded bg-secondary motion-reduce:animate-none" />
            <div className="h-4 w-1/6 animate-pulse rounded bg-secondary motion-reduce:animate-none" />
            <div className="hidden h-4 flex-1 animate-pulse rounded bg-secondary motion-reduce:animate-none sm:block" />
            <div className="h-4 w-16 animate-pulse rounded bg-secondary motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** A labelled filter bar above a list; wraps on narrow screens. */
export function FilterBar({ children, label = "Filters" }: { children: React.ReactNode; label?: string }) {
  return (
    <div role="search" aria-label={label} className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      {children}
    </div>
  );
}
