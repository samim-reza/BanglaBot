"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { PhoneOutgoing, PlusCircle, Search } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { OrderStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatMoney, humanize } from "@/lib/format";
import { ORDER_STATUSES, callLocked, formatApiError, ordersApi, type Order, type OrderStatus } from "@/services/api";

const PAGE_SIZE = 20;

export default function OrdersPage() {
  const toast = useAppToast();
  const [items, setItems] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [callingId, setCallingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await ordersApi.list({ page, page_size: PAGE_SIZE, status, search });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load orders."));
    } finally {
      setLoading(false);
    }
  }, [page, status, search]);

  useEffect(() => {
    void load();
  }, [load]);

  // Debounce typed search into the query.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  // Auto-refresh while any row is mid-call so outcomes land without a reload.
  const anyCalling = items.some((order) => order.status === "calling");
  useEffect(() => {
    if (!anyCalling) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [anyCalling, load]);

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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Orders"
        subtitle="Every order and where its confirmation call stands."
        actions={
          <Button asChild>
            <Link href="/orders/new">
              <PlusCircle className="h-4 w-4" />
              New order
            </Link>
          </Button>
        }
      />
      <ApiError message={error} />

      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search by customer, phone or order ref"
          />
        </div>
        <Select
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
              {humanize(value)}
            </option>
          ))}
        </Select>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading orders…</p>
      ) : items.length === 0 ? (
        <EmptyState title="No orders match">
          {search || status ? "Try clearing the search or status filter." : "Create an order to get started."}
        </EmptyState>
      ) : (
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Items</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-center">Attempts</TableHead>
                <TableHead>Last call</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((order) => {
                const locked = callLocked(order.status);
                const busy = callingId === order.id;
                return (
                  <TableRow key={order.id}>
                    <TableCell>
                      <Link href={`/orders/${order.id}`} className="font-medium hover:underline">
                        {order.customer_name}
                      </Link>
                      {order.order_ref && <div className="text-xs text-muted-foreground">Ref {order.order_ref}</div>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">{order.customer_phone}</TableCell>
                    <TableCell className="max-w-[16rem] truncate text-muted-foreground" title={order.items_summary ?? undefined}>
                      {order.items_summary || "—"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right tabular-nums">{formatMoney(order.total_amount, order.currency)}</TableCell>
                    <TableCell>
                      <OrderStatusBadge status={order.status} />
                    </TableCell>
                    <TableCell className="text-center tabular-nums">{order.call_attempts}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(order.last_call_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          disabled={locked || busy}
                          title={locked ? `Cannot call while ${humanize(order.status).toLowerCase()}` : "Place confirmation call"}
                          onClick={() => void placeCall(order)}
                        >
                          <PhoneOutgoing className="h-3.5 w-3.5" />
                          {busy ? "Dialing…" : "Call"}
                        </Button>
                        <Button asChild size="sm" variant="outline">
                          <Link href={`/orders/${order.id}`}>Details</Link>
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

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
    </div>
  );
}
