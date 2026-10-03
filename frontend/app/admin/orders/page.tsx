"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";

import { RecordStatusBadge } from "@/components/admin/badges";
import { FilterBar, LoadingRows } from "@/components/admin/states";
import { pageFrom, useUrlFilters } from "@/components/admin/url-filters";
import { useAdminMerchants, useAdminMeta, verticalOf } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import { formatInZone, statusLabel, t } from "@/lib/vertical";
import { ORDER_STATUSES, adminApi, formatApiError, type Merchant, type Order, type OrderStatus } from "@/services/api";

const PAGE_SIZE = 25;
const FILTER_KEYS = ["merchant_id", "status", "page"] as const;

export default function AdminRecordsPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading records…" />}>
      <RecordsView />
    </Suspense>
  );
}

function RecordsView() {
  const { meta } = useAdminMeta();
  const { merchants } = useAdminMerchants();
  const [filters, setFilters] = useUrlFilters(FILTER_KEYS);
  const merchantId = filters.merchant_id;
  const status = (ORDER_STATUSES as string[]).includes(filters.status) ? (filters.status as OrderStatus) : "";
  const page = pageFrom(filters.page);

  const [items, setItems] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const byId = useMemo(() => new Map<string, Merchant>(merchants.map((merchant) => [merchant.id, merchant])), [merchants]);
  const selected = merchantId ? byId.get(merchantId) ?? null : null;
  const selectedSpec = verticalOf(meta, selected?.vertical);

  const load = useCallback(async () => {
    try {
      const result = await adminApi.orders({ merchant_id: merchantId, status, page, page_size: PAGE_SIZE });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setItems([]);
      setTotal(0);
      setError(formatApiError(err, "Could not load records."));
    } finally {
      setLoading(false);
    }
  }, [merchantId, status, page]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  // Refresh while any listed record is mid-call, so outcomes land without a reload.
  const anyCalling = items.some((order) => order.status === "calling");
  useEffect(() => {
    if (!anyCalling) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [anyCalling, load]);

  const filtered = Boolean(merchantId || status);

  return (
    <>
      <PageHeader
        title={selected ? `Records · ${selected.business_name}` : "Records"}
        subtitle="Orders, appointments, viewings, jobs and leads across every account, newest first."
      />
      <ApiError message={error} />

      <FilterBar label="Filter records">
        <Select className="sm:w-64" aria-label="Account" value={merchantId} onChange={(event) => setFilters({ merchant_id: event.target.value, page: null })}>
          <option value="">All accounts</option>
          {merchantId && !selected && <option value={merchantId}>Selected account</option>}
          {merchants.map((merchant) => (
            <option key={merchant.id} value={merchant.id}>
              {merchant.business_name}
            </option>
          ))}
        </Select>
        <Select className="sm:w-52" aria-label="Status" value={status} onChange={(event) => setFilters({ status: event.target.value, page: null })}>
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((value) => (
            <option key={value} value={value}>
              {statusLabel(selectedSpec, value)}
            </option>
          ))}
        </Select>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => setFilters({ merchant_id: null, status: null, page: null })}>
            <X className="h-3.5 w-3.5" />
            Clear filters
          </Button>
        )}
        {selected && (
          <Link href={`/admin/merchants/${selected.id}`} className="text-sm font-medium text-primary hover:underline sm:ml-auto">
            View account
          </Link>
        )}
      </FilterBar>

      {loading && items.length === 0 ? (
        <LoadingRows label="Loading records…" />
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={filtered ? "No records match" : "No records yet"}>
            {filtered ? "Try another account or status." : "Records appear here as accounts add them or their agents capture them."}
          </EmptyState>
        )
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card" aria-busy={loading}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Summary</TableHead>
                <TableHead>Scheduled</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((order) => {
                const merchant = byId.get(order.merchant_id);
                const spec = verticalOf(meta, merchant?.vertical);
                const kind = spec && spec.record_kind === order.kind ? t(spec.record_label, humanize(order.kind)) : humanize(order.kind);
                const summary = order.summary || order.items_summary || "";
                return (
                  <TableRow key={order.id}>
                    <TableCell className="min-w-[10rem]">
                      <Link href={`/admin/merchants/${order.merchant_id}`} className="font-medium hover:text-primary hover:underline">
                        {order.merchant_name || merchant?.business_name || "Unknown account"}
                      </Link>
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{kind}</TableCell>
                    <TableCell className="min-w-[9rem]">
                      <div>{order.customer_name || "—"}</div>
                      {order.order_ref && <div className="text-xs text-muted-foreground">Ref {order.order_ref}</div>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap font-mono text-xs">
                      {order.customer_phone ? (
                        <a href={`tel:${order.customer_phone}`} className="hover:text-primary hover:underline">
                          {order.customer_phone}
                        </a>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="max-w-[18rem]">
                      <span className="line-clamp-2 text-muted-foreground" title={summary || undefined}>
                        {summary || "—"}
                      </span>
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {order.scheduled_at ? (
                        <>
                          {formatInZone(order.scheduled_at, merchant?.timezone)}
                          {merchant?.timezone && <div className="text-xs text-muted-foreground">{merchant.timezone}</div>}
                        </>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <RecordStatusBadge status={order.status} spec={spec} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(order.created_at)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={(next) => setFilters({ page: next })} />}
    </>
  );
}
