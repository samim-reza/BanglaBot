"use client";

import { Suspense, useMemo, useState } from "react";

import { AuditDrawer } from "@/components/admin/audit/audit-drawer";
import { AuditFilters } from "@/components/admin/audit/audit-filters";
import { AuditTable } from "@/components/admin/audit/audit-table";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { LoadingRows } from "@/components/admin/states";
import { useUrlFilters } from "@/components/admin/url-filters";
import { useAdminMerchants } from "@/components/admin/use-admin-meta";
import { useCursorList } from "@/components/admin/use-cursor-list";
import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { LoadMore } from "@/components/pagination";
import { auditApi, type AuditActorType, type AuditEvent } from "@/services/api/admin/audit";

const KEYS = ["action", "merchant_id", "actor", "actor_type"] as const;

export default function AdminAuditPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading the audit log…" />}>
      <AuditView />
    </Suspense>
  );
}

function AuditView() {
  const { can, loading } = useAdminMe();
  const { merchants } = useAdminMerchants();
  const [f, setFilters] = useUrlFilters(KEYS);
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const names = useMemo(() => new Map(merchants.map((m) => [m.id, m.business_name])), [merchants]);
  const params = { action: f.action, merchant_id: f.merchant_id, actor: f.actor, actor_type: f.actor_type as AuditActorType | "" };
  const list = useCursorList((cursor) => auditApi.list({ ...params, cursor, limit: 50 }), JSON.stringify(params), "Could not load the audit log.");
  const filtered = Boolean(f.action || f.merchant_id || f.actor || f.actor_type);

  if (!loading && !can("audit")) return <EmptyState title="Support or superadmin only" />;

  return (
    <>
      <PageHeader title="Audit log" />
      <AuditFilters values={f} merchants={merchants} onChange={setFilters} />
      <ApiError message={list.error} />
      {list.loading && list.items.length === 0 ? (
        <LoadingRows label="Loading the audit log…" />
      ) : list.items.length === 0 ? (
        list.error ? null : <EmptyState title={filtered ? "Nothing matches" : "No events yet"} />
      ) : (
        <div aria-busy={list.loading} className={list.loading ? "opacity-60 transition-opacity" : undefined}>
          <AuditTable items={list.items} names={names} onOpen={setOpen} />
        </div>
      )}
      {list.items.length > 0 && <LoadMore shown={list.items.length} hasMore={list.hasMore} loading={list.loadingMore} onLoadMore={() => void list.loadMore()} noun="events" />}
      <AuditDrawer event={open} names={names} onClose={() => setOpen(null)} />
    </>
  );
}
