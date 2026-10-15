import { fmtUsd } from "@/components/admin/numbers";

/** Money shown with 2 decimals, or 4 under a dollar-cent (per-minute / per-call costs). */
export const usd = (value: number | null | undefined) => fmtUsd(value, value !== null && value !== undefined && Math.abs(value) > 0 && Math.abs(value) < 0.01 ? 4 : 2);

/** "$0.00 · list $1.23": the actual cost, plus what it would have cost when free tiers / cache saved money. */
export function CostWithList({ cost, list, className }: { cost: number; list: number; className?: string }) {
  const saved = list - cost > 0.00005;
  return (
    <span className={className}>
      <span className="tabular-nums">{usd(cost)}</span>
      {saved && (
        <span className="text-xs text-muted-foreground" title="List (shadow) cost without free tiers or cache">
          {" "}
          · list {usd(list)}
        </span>
      )}
    </span>
  );
}
