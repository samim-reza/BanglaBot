import { fmtInt, fmtPercent, fmtUsd } from "@/components/admin/numbers";
import { KpiTile } from "@/components/admin/stats";
import type { FinanceOverview } from "@/services/api/admin/finance";

import { CostWithList, usd } from "./money";

/** The month's headline economics. */
export function FinanceKpis({ overview }: { overview: FinanceOverview }) {
  const o = overview;
  return (
    <section aria-label="Month figures" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <KpiTile label="Revenue" value={fmtUsd(o.revenue_usd)} hint={`${fmtInt(o.paying_accounts)} paying of ${fmtInt(o.accounts)} accounts`} />
      <KpiTile label="Cost" value={fmtUsd(o.cost_usd)} hint={<CostWithList cost={o.cost_usd} list={o.list_cost_usd} />} />
      <KpiTile label="Gross margin" value={fmtPercent(o.margin_pct, 1)} emphasis={o.margin_usd < 0} hint={fmtUsd(o.margin_usd)} />
      <KpiTile label="Cost per minute" value={usd(o.cost_per_minute_usd)} hint={`${fmtInt(o.minutes)} min · ${fmtInt(o.calls)} calls · ${fmtInt(o.chats)} chats`} />
      <KpiTile label="Cache savings" value={fmtUsd(o.cache_savings_usd)} hint="Audio served from cache" />
      <KpiTile label="Free-tier savings" value={fmtUsd(o.free_tier_savings_usd)} hint="List cost of free usage" />
    </section>
  );
}
