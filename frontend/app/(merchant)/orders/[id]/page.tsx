"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Pencil, PhoneOutgoing, Trash2 } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { CallLogList } from "@/components/call-log-list";
import { RecordForm, recordFieldValue, recordToFormValues, recordUpdatePayload } from "@/components/order-form";
import { PageHeader } from "@/components/page-header";
import { RecordSmsCard } from "@/components/sms-messages";
import type { FormValues } from "@/components/schema-form";
import { BADGE_BASE, OrderStatusBadge, SourceBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { displayValue, formatInZone, statusLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { ORDER_STATUSES, callLocked, formatApiError, ordersApi, type OrderDetail, type OrderStatus } from "@/services/api";

const WIDE_TYPES = new Set(["textarea", "list", "days", "multiselect"]);

/** Anything the agent stored (strings, numbers, flags, small objects) as readable text. */
function looseValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map((item) => looseValue(item)).join(", ");
  return JSON.stringify(value);
}

function KeyValueList({ entries }: { entries: Array<[string, string, boolean?]> }) {
  return (
    <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
      {entries.map(([label, value, wide]) => (
        <div key={label} className={cn("min-w-0", wide && "sm:col-span-2")}>
          <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
          <dd className="mt-0.5 whitespace-pre-wrap break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function RecordDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const toast = useAppToast();
  const { vertical, merchant, entitlements } = useWorkspace();
  const timezone = merchant.timezone;
  const singular = t(vertical.record_label, "Record");
  const plural = t(vertical.record_label_plural, "Records");
  // Outbound calls need a voice plan.
  const canCall = vertical.directions.includes("outbound") && entitlements.channels.includes("voice");
  const callName = t(vertical.outbound_label, "Call");
  const specs = vertical.record_fields;

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrder(await ordersApi.get(id));
      setError(null);
    } catch (err) {
      setError(formatApiError(err, `Could not load the ${singular.toLowerCase()}.`));
    }
  }, [id, singular]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while the agent is on the line so the outcome and log appear on their own.
  useEffect(() => {
    if (order?.status !== "calling") return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [order?.status, load]);

  const initialValues = useMemo<FormValues>(() => (order ? recordToFormValues(order, specs) : {}), [order, specs]);

  const save = async (values: FormValues) => {
    const { payload, kept } = recordUpdatePayload(specs, initialValues, values);
    if (!Object.keys(payload).length) {
      setEditing(false);
      if (kept.length) toast.error(`${kept.join(", ")} can't be left empty, so nothing was changed.`);
      return;
    }
    setBusy(true);
    try {
      await ordersApi.update(id, payload);
      await load();
      setEditing(false);
      toast.success(`${singular} updated.`);
      if (kept.length) toast.error(`${kept.join(", ")} can't be left empty and kept its old value.`);
    } catch (err) {
      toast.error(formatApiError(err, `Could not update the ${singular.toLowerCase()}.`));
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status: OrderStatus) => {
    setBusy(true);
    try {
      await ordersApi.update(id, { status });
      await load();
      toast.success(`Status set to ${statusLabel(vertical, status).toLowerCase()}.`);
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
    if (!window.confirm(`Delete this ${singular.toLowerCase()} for ${order.customer_name}? Its call history stays in Calls & chats.`)) return;
    setBusy(true);
    try {
      await ordersApi.remove(id);
      toast.success(`${singular} deleted.`);
      router.replace("/orders");
    } catch (err) {
      toast.error(formatApiError(err, `Could not delete the ${singular.toLowerCase()}.`));
      setBusy(false);
    }
  };

  const backLink = (
    <Button asChild variant="ghost" size="sm">
      <Link href="/orders">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {plural}
      </Link>
    </Button>
  );

  if (error && !order) {
    return (
      <div className="space-y-4">
        <ApiError message={error} />
        {backLink}
      </div>
    );
  }
  if (!order) {
    return (
      <div className="space-y-4" role="status" aria-label={`Loading ${singular.toLowerCase()}`}>
        <div className="h-8 w-56 animate-pulse rounded-md bg-secondary" />
        <div className="h-64 animate-pulse rounded-lg bg-secondary" />
      </div>
    );
  }

  const locked = callLocked(order.status, order.kind);
  const catalogNames = order.catalog_item_id && order.catalog_item_name ? { [order.catalog_item_id]: order.catalog_item_name } : {};
  const fmt = { currency: order.currency || merchant.currency, catalogNames, timezone };
  const notesSpec = specs.find((spec) => spec.key === "notes");
  const fieldEntries: Array<[string, string, boolean?]> = specs
    .filter((spec) => spec !== notesSpec)
    .map((spec) => [t(spec.label), displayValue(spec, recordFieldValue(order, spec), fmt), WIDE_TYPES.has(spec.type)]);
  const known = new Set(specs.map((spec) => spec.key));
  const extraEntries: Array<[string, string, boolean?]> = Object.entries(order.details ?? {})
    .filter(([key]) => !known.has(key) && !key.startsWith("_"))
    .map(([key, value]) => [humanize(key), looseValue(value)]);
  const flowEntries: Array<[string, string, boolean?]> = Object.entries(order.flow_data ?? {})
    .filter(([key, value]) => !key.startsWith("_") && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => [humanize(key), looseValue(value)]);
  const notes = notesSpec ? String(recordFieldValue(order, notesSpec) ?? "") : "";
  const odd = Boolean(order.kind) && order.kind !== vertical.record_kind;
  const statusChoices = ORDER_STATUSES.filter((value) => value !== "calling");

  return (
    <div className="space-y-6">
      <PageHeader
        title={order.customer_name}
        subtitle={[order.order_ref ? `${singular} ${order.order_ref}` : singular, order.summary].filter(Boolean).join(" · ")}
        actions={
          <>
            {backLink}
            {canCall && (
              <Button
                disabled={locked || busy}
                title={locked ? `No call while ${statusLabel(vertical, order.status).toLowerCase()}` : `Place a ${callName.toLowerCase()} now`}
                onClick={() => void placeCall()}
              >
                <PhoneOutgoing className="h-4 w-4" aria-hidden="true" />
                {order.status === "calling" ? "On the line…" : callName}
              </Button>
            )}
          </>
        }
      />
      <ApiError message={error} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>{singular}</CardTitle>
                <OrderStatusBadge status={order.status} spec={vertical} />
                <SourceBadge source={order.source} />
                {odd && <span className={cn(BADGE_BASE, "bg-secondary text-muted-foreground")}>{humanize(order.kind)}</span>}
              </div>
              {!editing && (
                <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={busy}>
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  Edit
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-5">
              {editing ? (
                <RecordForm initial={initialValues} submitLabel="Save changes" busy={busy} onSubmit={save} onCancel={() => setEditing(false)} />
              ) : (
                <>
                  <KeyValueList entries={fieldEntries} />
                  {notesSpec && (
                    <div className="rounded-md border border-border bg-surface p-3">
                      <p className="text-xs font-medium text-muted-foreground">{t(notesSpec.label)}</p>
                      <p className={cn("mt-1 whitespace-pre-wrap break-words text-sm", !notes && "text-muted-foreground")}>{notes || "No notes."}</p>
                    </div>
                  )}
                  {extraEntries.length > 0 && (
                    <div>
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">More details</p>
                      <KeyValueList entries={extraEntries} />
                    </div>
                  )}
                  <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
                    <span>Added {formatInZone(order.created_at, timezone)}</span>
                    {canCall && (
                      <span>
                        {order.call_attempts} call attempt{order.call_attempts === 1 ? "" : "s"}
                      </span>
                    )}
                    {order.last_call_at && <span>Last call {formatInZone(order.last_call_at, timezone)}</span>}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Collected by the agent</CardTitle>
              <CardDescription>From the latest call or chat.</CardDescription>
            </CardHeader>
            <CardContent>
              {flowEntries.length ? (
                <KeyValueList entries={flowEntries} />
              ) : (
                <p className="text-sm text-muted-foreground">Nothing collected yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
              <CardDescription>Set by your agent; change it anytime.</CardDescription>
            </CardHeader>
            <CardContent>
              <label className="flex flex-col gap-1.5 text-sm sm:max-w-xs">
                <span className="sr-only">Status</span>
                <Select
                  value={order.status}
                  disabled={busy || order.status === "calling"}
                  onChange={(event) => void setStatus(event.target.value as OrderStatus)}
                >
                  {order.status === "calling" && (
                    <option value="calling" disabled>
                      {statusLabel(vertical, "calling")}
                    </option>
                  )}
                  {statusChoices.map((value) => (
                    <option key={value} value={value}>
                      {statusLabel(vertical, value)}
                    </option>
                  ))}
                </Select>
                {order.status === "calling" && <span className="text-xs text-muted-foreground">Call in progress.</span>}
              </label>
            </CardContent>
          </Card>

          <Card className="border-destructive/40">
            <CardHeader>
              <CardTitle>Delete {singular.toLowerCase()}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-muted-foreground">Its calls and chats stay in your log.</p>
              <Button variant="destructive" size="sm" onClick={() => void remove()} disabled={busy || order.status === "calling"}>
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                Delete
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="grid h-fit gap-6">
          <Card className="h-fit">
            <CardHeader>
              <CardTitle>Calls &amp; chats</CardTitle>
            </CardHeader>
            <CardContent>
              <CallLogList logs={order.call_logs ?? []} timezone={timezone} />
            </CardContent>
          </Card>
          <RecordSmsCard
            orderId={order.id}
            phone={order.customer_phone}
            timezone={timezone}
            recordLabel={singular.toLowerCase()}
            refreshKey={`${order.status}:${order.call_logs?.length ?? 0}`}
          />
        </div>
      </div>
    </div>
  );
}
