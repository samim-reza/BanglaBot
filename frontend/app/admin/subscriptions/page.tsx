"use client";

import { Suspense } from "react";
import { X } from "lucide-react";

import { useAdminMe } from "@/components/admin/shell/admin-me";
import { FilterBar, LoadingRows } from "@/components/admin/states";
import { SUB_KINDS, SUB_STATUSES } from "@/components/admin/subscriptions/subscription-bits";
import { SubscriptionsTable } from "@/components/admin/subscriptions/subscriptions-table";
import { useUrlFilters } from "@/components/admin/url-filters";
import { useAdminMerchants, useAdminMeta } from "@/components/admin/use-admin-meta";
import { useCursorList } from "@/components/admin/use-cursor-list";
import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { LoadMore } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { subscriptionsApi, type SubscriptionKind, type SubscriptionStatus } from "@/services/api/admin/subscriptions";

const FILTER_KEYS = ["status", "kind", "tier", "merchant_id"] as const;

export default function AdminSubscriptionsPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading subscriptions…" />}>
      <SubscriptionsView />
    </Suspense>
  );
}

function SubscriptionsView() {
  const { can, loading: meLoading } = useAdminMe();
  const { meta } = useAdminMeta();
  const { merchants } = useAdminMerchants();
  const [f, setFilters] = useUrlFilters(FILTER_KEYS);
  const params = { status: f.status as SubscriptionStatus | "", kind: f.kind as SubscriptionKind | "", tier: f.tier, merchant_id: f.merchant_id };
  const key = JSON.stringify(params);
  const list = useCursorList((cursor) => subscriptionsApi.list({ ...params, cursor, limit: 50 }), key, "Could not load subscriptions.");
  const filtered = Boolean(f.status || f.kind || f.tier || f.merchant_id);

  if (!meLoading && !can("subscriptions")) return <EmptyState title="Not available for your role" />;

  return (
    <>
      <PageHeader title="Subscriptions" />
      <FilterBar label="Filter subscriptions">
        <Select className="sm:w-56" aria-label="Account" value={f.merchant_id} onChange={(e) => setFilters({ merchant_id: e.target.value })}>
          <option value="">All accounts</option>
          {merchants.map((m) => (
            <option key={m.id} value={m.id}>
              {m.business_name}
            </option>
          ))}
        </Select>
        <Select className="sm:w-40" aria-label="Status" value={f.status} onChange={(e) => setFilters({ status: e.target.value })}>
          <option value="">Any status</option>
          {SUB_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <Select className="sm:w-40" aria-label="Kind" value={f.kind} onChange={(e) => setFilters({ kind: e.target.value })}>
          <option value="">Any kind</option>
          {SUB_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </Select>
        <Select className="sm:w-40" aria-label="Plan" value={f.tier} onChange={(e) => setFilters({ tier: e.target.value })}>
          <option value="">Any plan</option>
          {meta?.plans.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
            </option>
          ))}
        </Select>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => setFilters({ status: null, kind: null, tier: null, merchant_id: null })}>
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        )}
      </FilterBar>
      <ApiError message={list.error} />
      {list.loading && list.items.length === 0 ? (
        <LoadingRows label="Loading subscriptions…" />
      ) : list.items.length === 0 ? (
        list.error ? null : <EmptyState title={filtered ? "Nothing matches" : "No subscriptions yet"} />
      ) : (
        <SubscriptionsTable items={list.items} />
      )}
      {list.items.length > 0 && <LoadMore shown={list.items.length} hasMore={list.hasMore} loading={list.loadingMore} onLoadMore={() => void list.loadMore()} noun="subscriptions" />}
    </>
  );
}
