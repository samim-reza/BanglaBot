"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { Check, X } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { adminApi, formatApiError, type AddonRequestStatus, type AdminAddonRequest } from "@/services/api";

import { Pill, type Tone } from "./badges";

/** Fired after an add-on request is approved or declined, so counts (nav badge, overview) refresh. */
export const ADDON_REQUESTS_CHANGED_EVENT = "admin:addon-requests-changed";

export function notifyAddonRequestsChanged() {
  window.dispatchEvent(new Event(ADDON_REQUESTS_CHANGED_EVENT));
}

const STATUS: Record<AddonRequestStatus, { label: string; tone: Tone }> = {
  pending: { label: "Pending", tone: "amber" },
  approved: { label: "Approved", tone: "green" },
  declined: { label: "Declined", tone: "red" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export function AddonRequestStatusPill({ status }: { status: AddonRequestStatus | string }) {
  const entry = STATUS[status as AddonRequestStatus];
  return <Pill tone={entry?.tone ?? "neutral"}>{entry?.label ?? status}</Pill>;
}

/**
 * One add-on request: what was asked for, the owner's note, and — while
 * pending — Approve / Decline with an optional note back to the owner.
 * `account` adds the account name and plan (for the all-accounts list).
 */
export function AddonRequestRow({
  request,
  account,
  onDecided,
  className,
}: {
  request: AdminAddonRequest;
  account?: { href: string; plan: string };
  onDecided: (updated: AdminAddonRequest) => void;
  className?: string;
}) {
  const toast = useAppToast();
  const noteId = useId();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "decline" | null>(null);
  const pending = request.status === "pending";

  const decide = async (decision: "approve" | "decline") => {
    setBusy(decision);
    try {
      const updated = await adminApi.decideAddonRequest(request.id, decision, note.trim());
      toast.success(decision === "approve" ? `${request.addon_name} switched on.` : "Request declined.");
      notifyAddonRequestsChanged();
      onDecided(updated);
    } catch (err) {
      toast.error(formatApiError(err, "Could not update the request."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={cn("flex flex-col gap-3 py-3 lg:flex-row lg:items-center lg:justify-between", className)}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {account && (
            <>
              <Link href={account.href} className="font-semibold hover:text-primary hover:underline">
                {request.merchant_name || "Account"}
              </Link>
              <span className="text-xs text-muted-foreground">{account.plan}</span>
              <span aria-hidden="true" className="text-muted-foreground">
                ·
              </span>
            </>
          )}
          <span className={cn(account ? "font-medium" : "font-semibold")}>
            {request.addon_name}
            {request.quantity > 1 && <span className="text-muted-foreground"> ×{request.quantity}</span>}
          </span>
          {request.price_label && <span className="text-sm tabular-nums text-muted-foreground">{request.price_label}</span>}
          {!pending && <AddonRequestStatusPill status={request.status} />}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {formatDateTime(request.created_at)}
          {request.decided_at && !pending ? ` · decided ${formatDateTime(request.decided_at)}` : ""}
        </p>
        {request.note && <p className="mt-1 break-words text-sm italic text-muted-foreground">“{request.note}”</p>}
        {request.admin_note && !pending && <p className="mt-1 break-words text-sm">Reply: {request.admin_note}</p>}
      </div>

      {pending && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center lg:shrink-0">
          <label htmlFor={noteId} className="sr-only">
            Note to the owner (optional)
          </label>
          <Input
            id={noteId}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Note (optional)"
            maxLength={500}
            className="h-9 sm:w-52"
            disabled={busy !== null}
          />
          <div className="flex gap-2">
            <Button size="sm" className="h-9 flex-1 sm:flex-none" onClick={() => void decide("approve")} disabled={busy !== null}>
              <Check className="h-4 w-4" />
              {busy === "approve" ? "Approving…" : "Approve"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-9 flex-1 sm:flex-none"
              onClick={() => void decide("decline")}
              disabled={busy !== null}
            >
              <X className="h-4 w-4" />
              {busy === "decline" ? "Declining…" : "Decline"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
