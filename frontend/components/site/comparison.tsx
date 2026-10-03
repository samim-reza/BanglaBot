import { COMPARISON, COMPARISON_SOURCES } from "@/lib/site-content";
import { cn } from "@/lib/utils";

/** What answering the phone costs today vs. the Growth plan. */
export function Comparison() {
  return (
    <div>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {COMPARISON.map((row) => (
          <li
            key={row.option}
            className={cn(
              "flex flex-col rounded-xl border p-5",
              row.ours ? "border-primary bg-accent ring-1 ring-primary" : "border-border bg-card",
            )}
          >
            <h3 className={cn("text-sm font-semibold", row.ours ? "text-accent-foreground" : "text-muted-foreground")}>
              {row.option}
            </h3>
            <p className="mt-3 text-2xl font-bold tracking-tight tabular-nums text-foreground">{row.cost}</p>
            <p className="text-xs font-medium text-muted-foreground">{row.unit}</p>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{row.detail}</p>
          </li>
        ))}
      </ul>
      <p className="mt-5 text-xs leading-relaxed text-muted-foreground">
        <span className="font-semibold">Sources: </span>
        {COMPARISON_SOURCES}
      </p>
    </div>
  );
}
