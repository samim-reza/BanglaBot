"use client";

import { LoadingRows } from "@/components/admin/states";
import { ApiError } from "@/components/api-error";

import { BreakdownCard } from "./breakdown-card";
import { CategoryBars } from "./category-bars";
import { FinanceKpis } from "./finance-kpis";
import { ForecastCard } from "./forecast-card";
import { useFinanceOverview } from "./use-finance-overview";

/** The month at a glance: KPIs, cost by category, forecast and the breakdown table. */
export function FinanceOverviewTab({ month }: { month: string }) {
  const { overview, forecast, error, loading } = useFinanceOverview(month);
  if (!overview) return error ? <ApiError message={error} /> : <LoadingRows label="Loading finance…" rows={6} />;
  return (
    <div className={loading ? "space-y-6 opacity-60 transition-opacity" : "space-y-6"} aria-busy={loading}>
      <ApiError message={error} />
      <FinanceKpis overview={overview} />
      <div className="grid gap-6 lg:grid-cols-2">
        <CategoryBars items={overview.by_category} />
        {forecast && <ForecastCard forecast={forecast} />}
      </div>
      <BreakdownCard month={month} />
    </div>
  );
}
