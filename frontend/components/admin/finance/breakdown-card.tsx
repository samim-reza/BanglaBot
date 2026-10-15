"use client";

import { useEffect, useState } from "react";

import { Segments } from "@/components/agent-flow/bits";
import { DialogError } from "@/components/admin/overlay";
import { fmtInt, fmtUsd } from "@/components/admin/numbers";
import { RatioBar } from "@/components/admin/voice/ratio-bar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatApiError } from "@/services/api";
import { financeApi, type BreakdownBy, type FinanceBreakdown } from "@/services/api/admin/finance";

import { categoryLabel } from "./labels";
import { CostWithList } from "./money";

const BY: { value: BreakdownBy; label: string }[] = [
  { value: "category", label: "Category" },
  { value: "provider", label: "Provider" },
  { value: "model", label: "Model" },
  { value: "vertical", label: "Business type" },
  { value: "account", label: "Account" },
];

/** Where the month's cost went, by one dimension (top 50). */
export function BreakdownCard({ month }: { month: string }) {
  const [by, setBy] = useState<BreakdownBy>("provider");
  const [data, setData] = useState<FinanceBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    financeApi
      .breakdown(by, month)
      .then((result) => !cancelled && (setData(result), setError(null)))
      .catch((err) => !cancelled && setError(formatApiError(err, "Could not load the breakdown.")))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [by, month]);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle>Breakdown</CardTitle>
        <Segments label="Group by" value={by} onChange={setBy} options={BY} size="sm" />
      </CardHeader>
      {error && (
        <CardContent>
          <DialogError message={error} />
        </CardContent>
      )}
      <div aria-busy={loading} className={loading && data ? "opacity-60 transition-opacity" : undefined}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{BY.find((item) => item.value === by)?.label}</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="w-40">Share</TableHead>
              <TableHead className="text-right">Cache saved</TableHead>
              <TableHead className="text-right">Free tier saved</TableHead>
              <TableHead className="text-right" title="Usage lines metered">
                Events
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">
                  No usage this month.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((item) => (
              <TableRow key={item.key}>
                <TableCell className="min-w-[10rem]">
                  <div className="font-medium">{by === "category" ? categoryLabel(item.key) : item.label || item.key}</div>
                  {(item.provider || item.category) && by !== "category" && (
                    <div className="text-xs text-muted-foreground">{[item.provider, item.category && categoryLabel(item.category)].filter(Boolean).join(" · ")}</div>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  <CostWithList cost={item.cost_usd} list={item.list_cost_usd} />
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <RatioBar ratio={item.share_pct / 100} label={`${item.label} share`} className="h-1.5" />
                    <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">{item.share_pct.toFixed(0)}%</span>
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">{fmtUsd(item.cache_savings_usd)}</TableCell>
                <TableCell className="text-right tabular-nums">{fmtUsd(item.free_tier_savings_usd)}</TableCell>
                <TableCell className="text-right tabular-nums">{fmtInt(item.events)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
