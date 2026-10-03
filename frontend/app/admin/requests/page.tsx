"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { AddonRequestRow } from "@/components/admin/addon-requests";
import { LoadingRows } from "@/components/admin/states";
import { useUrlFilters } from "@/components/admin/url-filters";
import { planName, useAdminMeta } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { adminApi, formatApiError, type AdminAddonRequest } from "@/services/api";

const FILTER_KEYS = ["status"] as const;

type View = "pending" | "all";

const TABS: { value: View; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "all", label: "All" },
];

export default function AdminRequestsPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading requests…" />}>
      <RequestsView />
    </Suspense>
  );
}

function RequestsView() {
  const { meta } = useAdminMeta();
  const [filters, setFilters] = useUrlFilters(FILTER_KEYS);
  const view: View = filters.status === "all" ? "all" : "pending";

  const [items, setItems] = useState<AdminAddonRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await adminApi.addonRequests(view);
      setItems(result.items);
      setError(null);
    } catch (err) {
      setItems([]);
      setError(formatApiError(err, "Could not load add-on requests."));
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    void load();
  }, [load]);

  const pendingCount = items.filter((item) => item.status === "pending").length;
  const replace = (updated: AdminAddonRequest) =>
    setItems((current) => current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));

  return (
    <>
      <PageHeader
        title="Add-on requests"
        subtitle="Approve to switch the add-on on."
        actions={
          <Button variant="outline" onClick={() => void load()} disabled={loading} aria-label="Refresh requests">
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin motion-reduce:animate-none")} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        }
      />
      <ApiError message={error} />

      <div role="group" aria-label="Filter by status" className="flex gap-1">
        {TABS.map((tab) => {
          const active = view === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              aria-pressed={active}
              onClick={() => setFilters({ status: tab.value === "all" ? "all" : null })}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active ? "border-primary bg-accent text-accent-foreground" : "border-border bg-card text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              {tab.label}
              {tab.value === "pending" && !loading && (
                <span className={cn("rounded-full px-1.5 text-xs tabular-nums", active ? "bg-primary text-primary-foreground" : "bg-secondary")}>
                  {pendingCount}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {loading && items.length === 0 ? (
        <LoadingRows label="Loading requests…" rows={4} />
      ) : items.length === 0 ? (
        error ? null : <EmptyState title={view === "pending" ? "No pending requests" : "No requests yet"} />
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card px-4" aria-busy={loading}>
          {items.map((request) => (
            <li key={request.id}>
              <AddonRequestRow
                request={request}
                account={{
                  href: `/admin/merchants/${encodeURIComponent(request.merchant_id)}`,
                  plan: planName(meta, request.merchant_plan),
                }}
                onDecided={replace}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
