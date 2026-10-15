"use client";

import Link from "next/link";
import { BadgeCheck, Check, X } from "lucide-react";

import { CopyButton } from "@/components/admin/copy-button";
import { fmtUsd } from "@/components/admin/numbers";
import { useAdminMeta, verticalName } from "@/components/admin/use-admin-meta";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { Signup } from "@/services/api/admin/signups";

import { SignupStatusPill } from "./signup-status";

export function SignupsTable({ items, onDecide }: { items: Signup[]; onDecide: (signup: Signup, decision: "approve" | "reject") => void }) {
  const { meta } = useAdminMeta();
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>When</TableHead>
            <TableHead>Business</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>Plan</TableHead>
            <TableHead>Payment</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((s) => {
            const open = s.status === "awaiting_approval" || s.status === "pending_payment";
            return (
              <TableRow key={s.id}>
                <TableCell className="whitespace-nowrap">{formatDateTime(s.created_at)}</TableCell>
                <TableCell className="min-w-[10rem]">
                  <Link href={`/admin/merchants/${s.merchant_id}`} className="font-medium hover:text-primary hover:underline">
                    {s.business_name || "—"}
                  </Link>
                  <div className="text-xs text-muted-foreground">
                    {s.owner_name}
                    {s.phone ? ` · ${s.phone}` : ""}
                  </div>
                </TableCell>
                <TableCell className="min-w-[12rem]">
                  <div className="flex items-center gap-1.5 break-all text-[13px]">
                    {s.email}
                    {s.email_verified && <BadgeCheck className="h-3.5 w-3.5 shrink-0 text-primary" aria-label="Verified" />}
                  </div>
                  {!s.email_verified && s.verify_url && (
                    <div className="mt-1">
                      <CopyButton value={s.verify_url} label="Verify link" title="No mail provider yet — send this link to the owner" />
                    </div>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <div className="font-medium">{humanize(s.tier)}</div>
                  <div className="text-xs text-muted-foreground">
                    {verticalName(meta, s.vertical)} · {s.region}
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  {s.subscription ? (
                    <>
                      <div className="tabular-nums">
                        {fmtUsd(s.subscription.amount)} <span className="text-xs text-muted-foreground">/ {s.subscription.interval}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{s.paid_at ? `Paid ${formatDateTime(s.paid_at)}` : humanize(s.subscription.status)}</div>
                    </>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>
                  <SignupStatusPill status={s.status} />
                  {s.admin_note && (
                    <div className="mt-1 max-w-[12rem] truncate text-xs text-muted-foreground" title={s.admin_note}>
                      {s.admin_note}
                    </div>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  {open && (
                    <span className="inline-flex gap-1.5">
                      <Button size="sm" onClick={() => onDecide(s, "approve")}>
                        <Check className="h-3.5 w-3.5" />
                        Approve
                      </Button>
                      <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" onClick={() => onDecide(s, "reject")}>
                        <X className="h-3.5 w-3.5" />
                        Reject
                      </Button>
                    </span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
