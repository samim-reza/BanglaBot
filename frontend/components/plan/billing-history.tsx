"use client";

/** Billing history (server cursor pages, "Load more"). */

import { useCallback } from "react";
import { History, LoaderCircle } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useCursorList } from "@/components/admin/use-cursor-list";
import { SectionCard, usd } from "@/components/portal/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, humanize } from "@/lib/format";
import { billingApi, type Subscription } from "@/services/api";

const TONE: Record<string, "success" | "warning" | "secondary"> = { active: "success", pending_payment: "warning", pending: "warning" };

export function BillingHistory({ refreshKey }: { refreshKey: string }) {
  const fetchPage = useCallback((cursor: string) => billingApi.subscriptions(cursor), []);
  const list = useCursorList<Subscription>(fetchPage, refreshKey, "Could not load billing history.");
  if (!list.loading && !list.error && list.items.length === 0) return null;

  return (
    <SectionCard id="billing" icon={History} title="Billing history">
      {list.error && <ApiError message={list.error} />}
      {list.loading ? (
        <div className="h-24 animate-pulse rounded-md bg-secondary" aria-busy="true" aria-label="Loading" />
      ) : (
        <div className="space-y-3">
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.items.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="whitespace-nowrap">{formatDate(row.activated_at || row.created_at)}</TableCell>
                    <TableCell>{row.tier_name || row.tier}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {row.current_period_start ? `${formatDate(row.current_period_start)} – ${formatDate(row.current_period_end)}` : row.interval === "year" ? "Yearly" : "Monthly"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{usd(row.amount)}</TableCell>
                    <TableCell>
                      <Badge variant={TONE[row.status] ?? "secondary"}>{humanize(row.status)}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {list.hasMore && (
            <Button type="button" variant="outline" size="sm" onClick={() => void list.loadMore()} disabled={list.loadingMore}>
              {list.loadingMore && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Load more
            </Button>
          )}
        </div>
      )}
    </SectionCard>
  );
}
