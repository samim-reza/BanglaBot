"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { OrderStatusBadge } from "@/components/status-badge";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatMoney, humanize } from "@/lib/format";
import { ORDER_STATUSES, adminApi, formatApiError, type Merchant, type Order, type OrderStatus } from "@/services/api";

const PAGE_SIZE = 25;

export default function AdminOrdersPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [merchantId, setMerchantId] = useState("");
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.merchants().then(setMerchants).catch(() => setMerchants([]));
  }, []);

  const load = useCallback(async () => {
    try {
      const result = await adminApi.orders({ merchant_id: merchantId, status, page, page_size: PAGE_SIZE });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load orders."));
    } finally {
      setLoading(false);
    }
  }, [merchantId, status, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const anyCalling = items.some((order) => order.status === "calling");
  useEffect(() => {
    if (!anyCalling) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [anyCalling, load]);

  const merchantName = (order: Order) => order.merchant_name ?? merchants.find((m) => m.id === order.merchant_id)?.business_name ?? order.merchant_id;

  return (
    <div className="space-y-6">
      <PageHeader title="Orders" subtitle="Orders across all merchants." />
      <ApiError message={error} />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Select
          className="sm:w-64"
          value={merchantId}
          onChange={(event) => {
            setMerchantId(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All merchants</option>
          {merchants.map((merchant) => (
            <option key={merchant.id} value={merchant.id}>
              {merchant.business_name}
            </option>
          ))}
        </Select>
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
        <EmptyState title="No orders match" />
      ) : (
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Merchant</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Items</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-center">Attempts</TableHead>
                <TableHead>Last call</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="font-medium">{merchantName(order)}</TableCell>
                  <TableCell>
                    <div>{order.customer_name}</div>
                    {order.order_ref && <div className="text-xs text-muted-foreground">Ref {order.order_ref}</div>}
                  </TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">{order.customer_phone}</TableCell>
                  <TableCell className="max-w-[14rem] truncate text-muted-foreground" title={order.items_summary ?? undefined}>
                    {order.items_summary || "—"}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right tabular-nums">{formatMoney(order.total_amount, order.currency)}</TableCell>
                  <TableCell>
                    <OrderStatusBadge status={order.status} />
                  </TableCell>
                  <TableCell className="text-center tabular-nums">{order.call_attempts}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(order.last_call_at)}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(order.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
    </div>
  );
}
