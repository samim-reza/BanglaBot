import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CategoryCost } from "@/services/api/admin/finance";

import { categoryLabel } from "./labels";
import { CostWithList } from "./money";

/**
 * Cost by category: one series → one hue, longest first, value at the bar's end.
 * The breakdown table below is its table view.
 */
export function CategoryBars({ items }: { items: CategoryCost[] }) {
  const rows = [...items].sort((a, b) => b.cost_usd - a.cost_usd);
  const max = Math.max(0.000001, ...rows.map((row) => row.cost_usd));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Cost by category</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No usage yet.</p>
        ) : (
          <ul className="space-y-3">
            {rows.map((row) => (
              <li key={row.category} title={`${categoryLabel(row.category)}: $${row.cost_usd.toFixed(4)} (list $${row.list_cost_usd.toFixed(4)})`}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium">{categoryLabel(row.category)}</span>
                  <CostWithList cost={row.cost_usd} list={row.list_cost_usd} className="font-semibold" />
                </div>
                <div className="mt-1.5 h-2.5 w-full" aria-hidden="true">
                  <div className="h-full rounded-r-[4px] bg-primary" style={{ width: row.cost_usd ? `${Math.max(1, (row.cost_usd / max) * 100)}%` : "0%" }} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
