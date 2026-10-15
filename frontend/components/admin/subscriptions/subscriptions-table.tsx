"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";

import { fmtUsd } from "@/components/admin/numbers";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatDateTime, humanize } from "@/lib/format";
import type { Subscription } from "@/services/api/admin/subscriptions";

import { SUB_KINDS, SubscriptionDetail, SubscriptionStatusPill } from "./subscription-bits";

export function SubscriptionsTable({ items }: { items: Subscription[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <span className="sr-only">Details</span>
            </TableHead>
            <TableHead>When</TableHead>
            <TableHead>Account</TableHead>
            <TableHead>Plan</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead className="text-right" title="Charged each period">
              Recurring
            </TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Kind</TableHead>
            <TableHead>Period end</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((sub) => {
            const expanded = open === sub.id;
            return (
              <Fragment key={sub.id}>
                <TableRow>
                  <TableCell className="py-1.5">
                    <Button variant="ghost" size="icon" className="h-8 w-8" aria-expanded={expanded} aria-label={expanded ? "Hide details" : "Show details"} onClick={() => setOpen(expanded ? null : sub.id)}>
                      {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </Button>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{formatDateTime(sub.created_at)}</TableCell>
                  <TableCell className="min-w-[9rem]">
                    <Link href={`/admin/merchants/${sub.merchant_id}`} className="font-medium hover:text-primary hover:underline">
                      {sub.merchant_name || "Unknown account"}
                    </Link>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {sub.tier_name || humanize(sub.tier)}
                    <span className="text-xs text-muted-foreground"> · {sub.interval === "year" ? "yearly" : "monthly"}</span>
                    {Object.keys(sub.addons ?? {}).length > 0 && <div className="text-xs text-muted-foreground">+{Object.keys(sub.addons).length} add-ons</div>}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right tabular-nums">{fmtUsd(sub.amount)}</TableCell>
                  <TableCell className="whitespace-nowrap text-right tabular-nums">{fmtUsd(sub.recurring_amount)}</TableCell>
                  <TableCell>
                    <SubscriptionStatusPill status={sub.status} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{SUB_KINDS.find((k) => k.value === sub.kind)?.label ?? humanize(sub.kind)}</TableCell>
                  <TableCell className="whitespace-nowrap">{formatDate(sub.current_period_end)}</TableCell>
                </TableRow>
                {expanded && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={9} className="bg-surface">
                      <SubscriptionDetail sub={sub} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
