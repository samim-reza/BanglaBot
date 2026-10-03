"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarClock, CirclePlus, PhoneOutgoing, Search } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { BulkCallControls } from "@/components/bulk-call-controls";
import { catalogNamesOf, recordFieldValue } from "@/components/order-form";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { BADGE_BASE, OrderStatusBadge, SourceBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { displayValue, formatInZone, statusLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { ORDER_STATUSES, callLocked, formatApiError, ordersApi, type Order, type OrderStatus } from "@/services/api";

const PAGE_SIZE = 20;

function kindLabel(kind: string): string {
  if (!kind) return "Record";
  return kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
}

export default function RecordsPage() {
  const toast = useAppToast();
  const { vertical, merchant, entitlements } = useWorkspace();
  const timezone = merchant.timezone;
  const singular = t(vertical.record_label, "Record");
  const plural = t(vertical.record_label_plural, "Records");
  // Outbound calls need a voice plan.
  const canCall = vertical.directions.includes("outbound") && entitlements.channels.includes("voice");
  const callName = t(vertical.outbound_label, "Call");

  const [items, setItems] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [upcoming, setUpcoming] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [callingId, setCallingId] = useState<string | null>(null);

  // Deep links from the dashboard tiles: /orders?status=confirmed (read once; no Suspense needed).
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("status");
    if (fromUrl && (ORDER_STATUSES as string[]).includes(fromUrl)) setStatus(fromUrl as OrderStatus);
    if (new URLSearchParams(window.location.search).get("upcoming") === "1" && vertical.scheduled) setUpcoming(true);
    setReady(true);
  }, [vertical.scheduled]);

  const load = useCallback(async () => {
    try {
      const result = await ordersApi.list({
        page,
        page_size: PAGE_SIZE,
        status,
        search,
        ...(upcoming ? { upcoming: true, sort: "scheduled" as const } : {}),
      });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, `Could not load ${plural.toLowerCase()}.`));
    } finally {
      setLoading(false);
    }
  }, [page, status, search, upcoming, plural]);

  useEffect(() => {
    if (ready) void load();
  }, [load, ready]);

  // Debounce typed search into the query.
  useEffect(() => {
    const next = searchInput.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setSearch(next);
      setPage(1);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput, search]);

  // Auto-refresh while any row is mid-call so outcomes land without a reload.
  const anyCalling = items.some((order) => order.status === "calling");
  useEffect(() => {
    if (!anyCalling) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [anyCalling, load]);

  const columns = useMemo(() => vertical.record_fields.filter((spec) => spec.list_column), [vertical.record_fields]);
  // The summary repeats the doctor / service column for catalog-based records.
  const showSummary = !columns.some((spec) => spec.type === "catalog");
  const catalogNames = useMemo(() => catalogNamesOf(items), [items]);

  const placeCall = async (order: Order) => {
    setCallingId(order.id);
    try {
      const updated = await ordersApi.call(order.id);
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      toast.success(`Calling ${order.customer_name}…`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not place the call."));
      void load();
    } finally {
      setCallingId(null);
    }
  };

  const filtered = Boolean(search || status || upcoming);

  return (
    <div className="space-y-6">
      <PageHeader
        title={plural}
        subtitle="Taken by your agent or added by you."
        actions={
          <Button asChild>
            <Link href="/orders/new">
              <CirclePlus className="h-4 w-4" aria-hidden="true" />
              New {singular.toLowerCase()}
            </Link>
          </Button>
        }
      />
      <ApiError message={error} />

      {canCall && <BulkCallControls onOrdersChanged={load} />}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <Input
            type="search"
            aria-label={`Search ${plural.toLowerCase()}`}
            className="pl-9"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search by name, phone or reference"
          />
        </div>
        <Select
          aria-label="Filter by status"
          className="sm:w-48"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as OrderStatus | "");
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((value) => (
            <option key={value} value={value}>
              {statusLabel(vertical, value)}
            </option>
          ))}
        </Select>
        {vertical.scheduled && (
          <button
            type="button"
            aria-pressed={upcoming}
            onClick={() => {
              setUpcoming((current) => !current);
              setPage(1);
            }}
            className={cn(
              "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              upcoming ? "border-primary bg-accent text-accent-foreground" : "border-border bg-card text-foreground hover:bg-secondary",
            )}
          >
            <CalendarClock className="h-4 w-4" aria-hidden="true" />
            Upcoming only
          </button>
        )}
      </div>

      {loading ? (
        <div className="space-y-2 rounded-lg border bg-card p-4" role="status" aria-label={`Loading ${plural.toLowerCase()}`}>
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-9 animate-pulse rounded-md bg-secondary" />
          ))}
        </div>
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={filtered ? `No ${plural.toLowerCase()} match` : `No ${plural.toLowerCase()} yet`}>
            {filtered ? (
              <button
                type="button"
                className="font-medium text-primary-dark hover:underline"
                onClick={() => {
                  setSearchInput("");
                  setSearch("");
                  setStatus("");
                  setUpcoming(false);
                  setPage(1);
                }}
              >
                Clear filters
              </button>
            ) : (
              <Link href="/orders/new" className="font-medium text-primary-dark hover:underline">
                New {singular.toLowerCase()}
              </Link>
            )}
          </EmptyState>
        )
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((spec) => (
                  <TableHead key={spec.key}>{t(spec.label)}</TableHead>
                ))}
                {showSummary && <TableHead>Summary</TableHead>}
                <TableHead>Status</TableHead>
                <TableHead className="hidden 2xl:table-cell">Source</TableHead>
                {canCall && <TableHead className="hidden 2xl:table-cell">Last call</TableHead>}
                <TableHead className="text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((order) => {
                const locked = callLocked(order.status, order.kind);
                const busy = callingId === order.id;
                const odd = Boolean(order.kind) && order.kind !== vertical.record_kind;
                return (
                  <TableRow key={order.id}>
                    {columns.map((spec, index) => {
                      const text = displayValue(spec, recordFieldValue(order, spec), {
                        currency: order.currency || merchant.currency,
                        catalogNames,
                        timezone,
                      });
                      if (index === 0) {
                        return (
                          <TableCell key={spec.key} className="min-w-40">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <Link href={`/orders/${order.id}`} className="font-medium text-foreground hover:underline">
                                {text}
                              </Link>
                              {odd && <span className={cn(BADGE_BASE, "bg-secondary px-2 text-[11.5px] text-muted-foreground")}>{kindLabel(order.kind)}</span>}
                            </div>
                            {order.order_ref && spec.key !== "order_ref" && (
                              <div className="text-xs text-muted-foreground">Ref {order.order_ref}</div>
                            )}
                          </TableCell>
                        );
                      }
                      return (
                        <TableCell
                          key={spec.key}
                          className={cn(
                            "text-muted-foreground",
                            spec.type === "phone" || spec.type === "datetime" || spec.type === "money" ? "whitespace-nowrap tabular-nums" : "max-w-[14rem] truncate",
                          )}
                          title={text}
                        >
                          {text}
                        </TableCell>
                      );
                    })}
                    {showSummary && (
                      <TableCell className="max-w-[18rem] truncate text-muted-foreground" title={order.summary || undefined}>
                        {order.summary || "—"}
                      </TableCell>
                    )}
                    <TableCell>
                      <OrderStatusBadge status={order.status} spec={vertical} />
                    </TableCell>
                    <TableCell className="hidden 2xl:table-cell">
                      <SourceBadge source={order.source} />
                    </TableCell>
                    {canCall && (
                      <TableCell className="hidden whitespace-nowrap text-muted-foreground 2xl:table-cell">
                        {order.last_call_at ? formatInZone(order.last_call_at, timezone) : "—"}
                        {order.call_attempts > 0 && (
                          <div className="text-xs">
                            {order.call_attempts} attempt{order.call_attempts === 1 ? "" : "s"}
                          </div>
                        )}
                      </TableCell>
                    )}
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1.5">
                        {canCall && (
                          <Button
                            size="sm"
                            disabled={locked || busy}
                            title={locked ? `No call while ${statusLabel(vertical, order.status).toLowerCase()}` : `Place a ${callName.toLowerCase()} now`}
                            aria-label={`${callName}: ${order.customer_name}`}
                            onClick={() => void placeCall(order)}
                          >
                            <PhoneOutgoing className="h-3.5 w-3.5" aria-hidden="true" />
                            {busy ? "Dialing…" : callName}
                          </Button>
                        )}
                        <Button asChild size="sm" variant="outline">
                          <Link href={`/orders/${order.id}`} aria-label={`Open ${order.customer_name}`}>
                            Open
                          </Link>
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {!loading && total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />}
    </div>
  );
}
