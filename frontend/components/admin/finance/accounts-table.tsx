"use client";

import Link from "next/link";

import { fmtInt, fmtPercent, fmtUsd } from "@/components/admin/numbers";
import { LoadingRows } from "@/components/admin/states";
import { useCursorList } from "@/components/admin/use-cursor-list";
import { useAdminMeta, verticalName } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { EmptyState } from "@/components/page-header";
import { LoadMore } from "@/components/pagination";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { financeApi } from "@/services/api/admin/finance";

import { CostWithList, usd } from "./money";

/** Per-account economics for the month (cursor-paginated). */
export function FinanceAccountsTable({ month }: { month: string }) {
  const { meta } = useAdminMeta();
  const list = useCursorList((cursor) => financeApi.accounts({ month, cursor, limit: 50 }), month, "Could not load accounts.");

  if (list.loading && list.items.length === 0) return <LoadingRows label="Loading accounts…" />;
  return (
    <div className="space-y-3">
      <ApiError message={list.error} />
      {list.items.length === 0 ? (
        list.error ? null : <EmptyState title="No accounts" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead className="text-right">Minutes</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">Revenue</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead className="text-right">Margin</TableHead>
                <TableHead className="text-right">Cost / min</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.items.map((row) => (
                <TableRow key={row.merchant_id} className={cn(!row.active && "text-muted-foreground")}>
                  <TableCell className="min-w-[11rem]">
                    <Link href={`/admin/merchants/${row.merchant_id}`} className="font-medium hover:text-primary hover:underline">
                      {row.business_name || "Unknown account"}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {verticalName(meta, row.vertical)} · {row.plan}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(row.minutes)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtInt(row.calls)}
                    {row.chats > 0 && <div className="text-xs text-muted-foreground">{fmtInt(row.chats)} chats</div>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmtUsd(row.revenue_usd)}</TableCell>
                  <TableCell className="whitespace-nowrap text-right">
                    <CostWithList cost={row.cost_usd} list={row.list_cost_usd} />
                  </TableCell>
                  <TableCell className={cn("whitespace-nowrap text-right tabular-nums", row.margin_usd < 0 && "font-semibold text-destructive")}>
                    {fmtUsd(row.margin_usd)}
                    <div className="text-xs text-muted-foreground">{fmtPercent(row.margin_pct)}</div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{usd(row.cost_per_minute_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {list.items.length > 0 && <LoadMore shown={list.items.length} hasMore={list.hasMore} loading={list.loadingMore} onLoadMore={() => void list.loadMore()} noun="accounts" />}
    </div>
  );
}
