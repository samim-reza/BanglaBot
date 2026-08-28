"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Pencil, PhoneOutgoing, Trash2 } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { CallLogList } from "@/components/call-log-list";
import { OrderForm, formValuesToInput, orderToFormValues, type OrderFormValues } from "@/components/order-form";
import { PageHeader } from "@/components/page-header";
import { OrderStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { formatDateTime, formatMoney, humanize } from "@/lib/format";
import { ORDER_STATUSES, callLocked, formatApiError, ordersApi, type OrderDetail, type OrderStatus } from "@/services/api";

function flowValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const toast = useAppToast();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrder(await ordersApi.get(id));
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load the order."));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while the agent is on the line so the outcome and log appear on their own.
  useEffect(() => {
    if (order?.status !== "calling") return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [order?.status, load]);

  const save = async (values: OrderFormValues) => {
    setBusy(true);
    try {
      await ordersApi.update(id, formValuesToInput(values));
      await load();
      setEditing(false);
      toast.success("Order updated.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not update the order."));
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status: OrderStatus) => {
    setBusy(true);
    try {
      await ordersApi.update(id, { status });
      await load();
      toast.success(`Status set to ${humanize(status).toLowerCase()}.`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not change the status."));
    } finally {
      setBusy(false);
    }
  };

  const placeCall = async () => {
    setBusy(true);
    try {
      const updated = await ordersApi.call(id);
      setOrder((current) => (current ? { ...current, ...updated } : current));
      toast.success(`Calling ${updated.customer_name}…`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not place the call."));
      void load();
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!order) return;
    if (!window.confirm(`Delete the order for ${order.customer_name}? This also removes its call logs.`)) return;
    setBusy(true);
    try {
      await ordersApi.remove(id);
      toast.success("Order deleted.");
      router.replace("/orders");
    } catch (err) {
      toast.error(formatApiError(err, "Could not delete the order."));
      setBusy(false);
    }
  };

  if (error && !order) {
    return (
      <div className="space-y-4">
        <ApiError message={error} />
        <Button asChild variant="outline">
          <Link href="/orders">
            <ArrowLeft className="h-4 w-4" />
            Back to orders
          </Link>
        </Button>
      </div>
    );
  }
  if (!order) return <p className="text-sm text-muted-foreground">Loading order…</p>;

  const locked = callLocked(order.status);
  const flowEntries = Object.entries(order.flow_data ?? {});
  const fields: Array<[string, string]> = [
    ["Order ref", order.order_ref || "—"],
    ["Customer", order.customer_name],
    ["Phone", order.customer_phone],
    ["Amount", formatMoney(order.total_amount, order.currency)],
    ["Address", order.address || "—"],
    ["Items", order.items_summary || "—"],
    ["Notes", order.notes || "—"],
    ["Created", formatDateTime(order.created_at)],
    ["Last call", formatDateTime(order.last_call_at)],
    ["Attempts", String(order.call_attempts)],
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={order.order_ref ? `Order ${order.order_ref}` : order.customer_name}
        subtitle={order.order_ref ? order.customer_name : undefined}
        actions={
          <>
            <Button asChild variant="ghost" size="sm">
              <Link href="/orders">
                <ArrowLeft className="h-4 w-4" />
                Orders
              </Link>
            </Button>
            <Button
              disabled={locked || busy}
              title={locked ? `Cannot call while ${humanize(order.status).toLowerCase()}` : "Place confirmation call"}
              onClick={() => void placeCall()}
            >
              <PhoneOutgoing className="h-4 w-4" />
              Call customer
            </Button>
          </>
        }
      />
      <ApiError message={error} />

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div className="flex items-center gap-3">
                <CardTitle>Order</CardTitle>
                <OrderStatusBadge status={order.status} />
              </div>
              {!editing && (
                <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={busy}>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {editing ? (
                <OrderForm initial={orderToFormValues(order)} submitLabel="Save changes" busy={busy} onSubmit={save} onCancel={() => setEditing(false)} />
              ) : (
                <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                  {fields.map(([label, value]) => (
                    <div key={label} className={label === "Address" || label === "Items" || label === "Notes" ? "sm:col-span-2" : undefined}>
                      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
                      <dd className="mt-0.5 whitespace-pre-wrap">{value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Select
                className="sm:w-56"
                value={order.status}
                disabled={busy || order.status === "calling"}
                onChange={(event) => void setStatus(event.target.value as OrderStatus)}
              >
                {ORDER_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {humanize(value)}
                  </option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">
                Override the outcome manually, e.g. after confirming by hand. The agent sets this automatically after each call.
              </p>
            </CardContent>
          </Card>

          {flowEntries.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>What the customer said</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                  {flowEntries.map(([key, value]) => (
                    <div key={key}>
                      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{humanize(key)}</dt>
                      <dd className="mt-0.5 whitespace-pre-wrap break-words">{flowValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          )}

          <Card className="border-destructive/40">
            <CardHeader>
              <CardTitle>Delete order</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-muted-foreground">Removes the order and its call history permanently.</p>
              <Button variant="destructive" size="sm" onClick={() => void remove()} disabled={busy}>
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Call history</CardTitle>
          </CardHeader>
          <CardContent>
            <CallLogList logs={order.call_logs ?? []} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
