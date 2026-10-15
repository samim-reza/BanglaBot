"use client";

import { useEffect, useState } from "react";

import { fmtUsd } from "@/components/admin/numbers";
import { formatApiError, isApiRequestError } from "@/services/api";
import { financeApi, type CallCosts as CallCostsData } from "@/services/api/admin/finance";

import { categoryLabel } from "./labels";
import { CostWithList, usd } from "./money";

const qty = (value: string, unit: string) => `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${unit}${Number(value) === 1 ? "" : "s"}`;

/** Cost lines of one call (telephony, STT, TTS incl. cache-served characters, LLM per model, SMS). */
export function CallCosts({ callLogId }: { callLogId: string }) {
  const [data, setData] = useState<CallCostsData | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    financeApi
      .callCosts(callLogId)
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setMessage(isApiRequestError(err) && err.status === 404 ? "No cost record." : formatApiError(err, "Could not load costs.")));
    return () => {
      cancelled = true;
    };
  }, [callLogId]);

  if (message) return <p className="text-xs text-muted-foreground">{message}</p>;
  if (!data) return <p className="text-xs text-muted-foreground">Loading costs…</p>;
  if (!data.metered || data.lines.length === 0) return <p className="text-xs text-muted-foreground">Not metered.</p>;

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-baseline gap-x-3 text-xs">
        <span className="font-semibold uppercase tracking-wide text-muted-foreground">Cost</span>
        <CostWithList cost={data.cost_usd} list={data.list_cost_usd} className="text-sm font-semibold" />
        {data.cache_savings_usd > 0 && <span className="text-muted-foreground">cache saved {fmtUsd(data.cache_savings_usd, 4)}</span>}
      </div>
      <table className="w-full max-w-2xl text-[12.5px]">
        <tbody>
          {data.lines.map((line, i) => (
            <tr key={`${line.sku}-${i}`} className="border-b border-border last:border-0">
              <td className="py-1 pr-2">{categoryLabel(line.category)}</td>
              <td className="py-1 pr-2 font-mono text-[11.5px] text-muted-foreground">
                {line.provider} · {line.sku}
              </td>
              <td className="py-1 pr-2 text-right tabular-nums">
                {qty(line.quantity, line.unit)}
                {line.cache_hit && <span className="ml-1 text-muted-foreground">(cache)</span>}
                {line.free_tier && <span className="ml-1 text-muted-foreground">(free)</span>}
              </td>
              <td className="py-1 text-right">
                <CostWithList cost={line.cost_usd} list={line.list_cost_usd} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <span className="sr-only">Total {usd(data.cost_usd)}</span>
    </div>
  );
}
