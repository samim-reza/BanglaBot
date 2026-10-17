import { CostWithList, usd } from "@/components/admin/finance/money";
import { fmtInt, fmtPercent, fmtUsd } from "@/components/admin/numbers";
import { KpiTile } from "@/components/admin/stats";
import type { FinanceOverview } from "@/services/api/admin/finance";

/** Month-to-date money figures (finance + superadmin only; nothing for other roles). */
export function FinanceTiles({ overview }: { overview: FinanceOverview | null }) {
  if (!overview) return null;
  return (
    <section aria-label="This month" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <KpiTile label="Revenue MTD" href="/admin/finance" value={fmtUsd(overview.revenue_usd, 0)} hint={`${fmtInt(overview.paying_accounts)} paying accounts`} />
      <KpiTile label="Cost MTD" href="/admin/finance" value={fmtUsd(overview.cost_usd, 0)} hint={<CostWithList cost={overview.cost_usd} list={overview.list_cost_usd} />} />
      <KpiTile
        label="Gross margin"
        value={fmtPercent(overview.margin_pct)}
        emphasis={overview.margin_usd < 0}
        hint={fmtUsd(overview.margin_usd, 0)}
      />
      <KpiTile label="Cost / min" value={usd(overview.cost_per_minute_usd)} hint={`${fmtInt(overview.minutes)} min · ${fmtInt(overview.calls)} calls`} />
      <KpiTile
        label="Savings"
        value={fmtUsd(overview.cache_savings_usd + overview.free_tier_savings_usd, 0)}
        hint={`Cache ${fmtUsd(overview.cache_savings_usd, 0)} · free tier ${fmtUsd(overview.free_tier_savings_usd, 0)}`}
      />
    </section>
  );
}
