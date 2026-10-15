"use client";

/** A record's payment: status chip, amount, the link (open / copy) and "Mark paid". */

import { useState } from "react";
import { CreditCard, ExternalLink, LoaderCircle } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { CopyButton, useCopy } from "@/components/portal/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInZone, money } from "@/lib/vertical";
import { formatApiError, isApiRequestError, ordersApi, type Order, type RecordPayment } from "@/services/api";

type Tone = "success" | "warning" | "secondary" | "danger";

const STATUS: Record<string, { label: string; tone: Tone }> = {
  at_venue: { label: "Pay on arrival", tone: "secondary" },
  pay_at_venue: { label: "Pay on arrival", tone: "secondary" },
  pending: { label: "Awaiting payment", tone: "warning" },
  link_pending: { label: "Link on its way", tone: "warning" },
  link_sent: { label: "Link sent", tone: "warning" },
  paid: { label: "Paid", tone: "success" },
  failed: { label: "Payment failed", tone: "danger" },
  refunded: { label: "Refunded", tone: "secondary" },
  expired: { label: "Link expired", tone: "secondary" },
};

const SETTLED = new Set(["paid", "refunded", "not_required"]);

export function paymentOf(order: Order): { status: string; block: RecordPayment; url: string } | null {
  const raw = order.details?.payment;
  const block = (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {}) as RecordPayment & { url?: string };
  const status = String(order.payment_status && order.payment_status !== "not_required" ? order.payment_status : block.status ?? "");
  if (!status || status === "not_required") return null;
  return { status, block, url: order.payment_url || String(block.url ?? "") };
}

export function PaymentChip({ status }: { status: string }) {
  const info = STATUS[status] ?? { label: status.replace(/_/g, " "), tone: "secondary" as Tone };
  if (info.tone === "danger") return <Badge className="bg-destructive/10 text-destructive">{info.label}</Badge>;
  return <Badge variant={info.tone}>{info.label}</Badge>;
}

export function PaymentCard({ order, timezone, onChanged }: { order: Order; timezone?: string; onChanged: () => void }) {
  const toast = useAppToast();
  const { copied, copy } = useCopy();
  const [busy, setBusy] = useState(false);
  const payment = paymentOf(order);
  if (!payment) return null;
  const { status, block, url } = payment;
  const amount = block.amount !== undefined && block.amount !== "" ? money(block.amount, block.currency || order.currency) : null;
  const method = block.method === "online" ? "Online" : block.method === "at_venue" ? "On arrival" : "";

  const markPaid = async () => {
    if (!window.confirm(`Mark ${amount ?? "this payment"} as paid?`)) return;
    setBusy(true);
    try {
      await ordersApi.markPaid(order.id);
      toast.success("Marked paid.");
      onChanged();
    } catch (err) {
      toast.error(isApiRequestError(err) && err.status === 404 ? "Marking paid isn't available yet." : formatApiError(err, "Could not mark it paid."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="h-fit">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-4 w-4 text-primary" aria-hidden />
          Payment
        </CardTitle>
        <PaymentChip status={status} />
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {(amount || method) && (
          <p>
            {amount && <span className="text-lg font-semibold tabular-nums">{amount}</span>}
            {method && <span className="ml-2 text-muted-foreground">{method}</span>}
          </p>
        )}
        {status === "paid" && block.paid_at && <p className="text-xs text-muted-foreground">Paid {formatInZone(block.paid_at, timezone)}</p>}
        {status === "pending" && block.hold_until && <p className="text-xs text-muted-foreground">Held until {formatInZone(block.hold_until, timezone)}</p>}
        {url && !SETTLED.has(status) && (
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <a href={url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                Open link
              </a>
            </Button>
            <CopyButton id="payment-link" text={url} copied={copied} onCopy={copy} label="Copy link" />
          </div>
        )}
        {!SETTLED.has(status) && (
          <Button type="button" size="sm" onClick={() => void markPaid()} disabled={busy}>
            {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            Mark paid
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
