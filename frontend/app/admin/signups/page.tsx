"use client";

import { Suspense, useState } from "react";

import { useAdminMe } from "@/components/admin/shell/admin-me";
import { SIGNUPS_CHANGED_EVENT } from "@/components/admin/shell/use-nav-badges";
import { DecisionDialog } from "@/components/admin/signups/decision-dialog";
import { SIGNUP_STATUSES } from "@/components/admin/signups/signup-status";
import { SignupsTable } from "@/components/admin/signups/signups-table";
import { FilterBar, LoadingRows } from "@/components/admin/states";
import { useUrlFilters } from "@/components/admin/url-filters";
import { useCursorList } from "@/components/admin/use-cursor-list";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, PageHeader } from "@/components/page-header";
import { LoadMore } from "@/components/pagination";
import { Select } from "@/components/ui/select";
import { signupsApi, type Signup, type SignupStatus } from "@/services/api/admin/signups";

const FILTER_KEYS = ["status"] as const;

export default function AdminSignupsPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading signups…" />}>
      <SignupsView />
    </Suspense>
  );
}

function SignupsView() {
  const { can, loading: meLoading } = useAdminMe();
  const toast = useAppToast();
  const [filters, setFilters] = useUrlFilters(FILTER_KEYS);
  // Default view: the ones waiting for a decision. "all" = no filter.
  const status = filters.status === "all" ? "" : ((filters.status || "awaiting_approval") as SignupStatus);
  const list = useCursorList((cursor) => signupsApi.list({ status, cursor, limit: 50 }), status, "Could not load signups.");
  const [target, setTarget] = useState<{ signup: Signup; decision: "approve" | "reject" } | null>(null);

  if (!meLoading && !can("signups")) return <EmptyState title="Support or superadmin only" />;

  const done = (updated: Signup) => {
    toast.success(updated.status === "approved" ? "Signup approved." : "Signup rejected.");
    setTarget(null);
    list.setItems((items) => (status && updated.status !== status ? items.filter((s) => s.id !== updated.id) : items.map((s) => (s.id === updated.id ? updated : s))));
    window.dispatchEvent(new Event(SIGNUPS_CHANGED_EVENT));
  };

  return (
    <>
      <PageHeader title="Signups" />
      <FilterBar label="Filter signups">
        <Select className="sm:w-56" aria-label="Status" value={status || "all"} onChange={(e) => setFilters({ status: e.target.value === "awaiting_approval" ? null : e.target.value })}>
          {SIGNUP_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
          <option value="all">All</option>
        </Select>
      </FilterBar>
      <ApiError message={list.error} />
      {list.loading && list.items.length === 0 ? (
        <LoadingRows label="Loading signups…" />
      ) : list.items.length === 0 ? (
        list.error ? null : <EmptyState title={status === "awaiting_approval" ? "Nothing to approve" : "No signups"} />
      ) : (
        <SignupsTable items={list.items} onDecide={(signup, decision) => setTarget({ signup, decision })} />
      )}
      {list.items.length > 0 && <LoadMore shown={list.items.length} hasMore={list.hasMore} loading={list.loadingMore} onLoadMore={() => void list.loadMore()} noun="signups" />}
      <DecisionDialog signup={target?.signup ?? null} decision={target?.decision ?? "approve"} onClose={() => setTarget(null)} onDone={done} />
    </>
  );
}
