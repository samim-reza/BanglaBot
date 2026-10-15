"use client";

import { CircleAlert, LogIn, Pencil, Trash2 } from "lucide-react";

import { ActiveBadge, Pill } from "@/components/admin/badges";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import type { AdminMerchantDetail } from "@/services/api";

/** Name, status and the account actions; a banner while the account is off. */
export function AccountHeader({
  detail,
  onEdit,
  onOpenPortal,
  onDelete,
}: {
  detail: AdminMerchantDetail;
  onEdit: () => void;
  onOpenPortal: () => void;
  onDelete: () => void;
}) {
  const { can } = useAdminMe();
  const { merchant, usage } = detail;
  const portalBlocked = !merchant.active ? "Activate the account first" : !can("impersonate") ? "Support or superadmin only" : undefined;

  return (
    <>
      <div className="flex flex-col justify-between gap-4 border-b border-border pb-4 md:flex-row md:items-end">
        <div className="min-w-0">
          <h1 className="break-words text-2xl font-semibold">{merchant.business_name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <ActiveBadge active={merchant.active} />
            <Pill tone="teal">{usage.plan.name}</Pill>
            <span className="font-mono text-xs">@{merchant.username}</span>
            <span aria-hidden="true">·</span>
            <span>Created {formatDate(merchant.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onEdit}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
          <Button onClick={onOpenPortal} disabled={Boolean(portalBlocked)} title={portalBlocked}>
            <LogIn className="h-4 w-4" />
            Open portal
          </Button>
          <Button variant="outline" className="text-destructive hover:text-destructive" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {!merchant.active && (
        <div className="flex items-start gap-3 rounded-md border border-[#fcd34d] bg-[#fef3c7] p-3 text-sm text-[#92400e] dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            This account is inactive: the owner can&apos;t sign in and the agent doesn&apos;t answer calls or chats. Turn it back on from{" "}
            <button type="button" className="font-semibold underline underline-offset-2" onClick={onEdit}>
              Edit
            </button>
            .
          </p>
        </div>
      )}
    </>
  );
}
