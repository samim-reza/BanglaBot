import { RatioBar } from "@/components/admin/voice/ratio-bar";
import { fmtInt, fmtPct, fmtUsd } from "@/components/admin/numbers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FinanceForecast } from "@/services/api/admin/finance";

import { categoryLabel } from "./labels";

function Projection({ label, mtd, forecast, money = true }: { label: string; mtd: number; forecast: number; money?: boolean }) {
  const show = (value: number) => (money ? fmtUsd(value, 0) : fmtInt(value));
  return (
    <div className="rounded-md border border-border p-3">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">{show(forecast)}</dd>
      <dd className="text-xs text-muted-foreground">{show(mtd)} so far</dd>
    </div>
  );
}

/** Month-end projection from the run rate so far. */
export function ForecastCard({ forecast }: { forecast: FinanceForecast }) {
  const f = forecast;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Month-end forecast</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>Month elapsed</span>
            <span className="tabular-nums">{fmtPct(f.fraction_elapsed)}</span>
          </div>
          <RatioBar ratio={f.fraction_elapsed} label="Month elapsed" />
        </div>
        <dl className="grid grid-cols-2 gap-3">
          <Projection label="Revenue" mtd={f.revenue_mtd_usd} forecast={f.revenue_forecast_usd} />
          <Projection label="Cost" mtd={f.cost_mtd_usd} forecast={f.cost_forecast_usd} />
          <div className="rounded-md border border-border p-3">
            <dt className="text-xs font-medium text-muted-foreground">Margin</dt>
            <dd className={f.margin_forecast_usd < 0 ? "mt-1 text-xl font-semibold text-destructive" : "mt-1 text-xl font-semibold"}>{fmtPct(f.margin_forecast_pct, 1)}</dd>
            <dd className="text-xs text-muted-foreground">{fmtUsd(f.margin_forecast_usd, 0)}</dd>
          </div>
          <Projection label="Minutes" mtd={f.minutes_mtd} forecast={f.minutes_forecast} money={false} />
        </dl>
        {f.by_category.length > 0 && (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-xs text-muted-foreground">
                <th className="py-1 text-left font-medium">Category</th>
                <th className="py-1 text-right font-medium">So far</th>
                <th className="py-1 text-right font-medium">Month end</th>
              </tr>
            </thead>
            <tbody>
              {f.by_category.map((row) => (
                <tr key={row.category} className="border-t border-border">
                  <td className="py-1.5">{categoryLabel(row.category)}</td>
                  <td className="py-1.5 text-right tabular-nums">{fmtUsd(row.cost_mtd_usd)}</td>
                  <td className="py-1.5 text-right tabular-nums">{fmtUsd(row.cost_forecast_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
