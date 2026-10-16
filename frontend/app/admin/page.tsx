"use client";

import Link from "next/link";
import { Plus, RefreshCw } from "lucide-react";

import { AccountsByType } from "@/components/admin/dashboard/accounts-by-type";
import { AttentionList } from "@/components/admin/dashboard/attention-list";
import { FinanceTiles } from "@/components/admin/dashboard/finance-tiles";
import { HealthStrip } from "@/components/admin/dashboard/health-strip";
import { KpiRow } from "@/components/admin/dashboard/kpi-row";
import { useDashboard } from "@/components/admin/dashboard/use-dashboard";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

export default function AdminDashboardPage() {
  const { can, loading } = useAdminMe();
  const { data, error, refreshing, refresh } = useDashboard({ finance: can("finance"), signups: can("signups"), ready: !loading });
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Today is from midnight, UTC."
        actions={
          <>
            <Button variant="outline" onClick={() => void refresh()} disabled={refreshing} aria-label="Refresh">
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin motion-reduce:animate-none" : ""}`} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <Button asChild>
              <Link href="/admin/merchants?create=1">
                <Plus className="h-4 w-4" />
                Create account
              </Link>
            </Button>
          </>
        }
      />
      <ApiError message={error} />
      <KpiRow data={data} />
      <FinanceTiles overview={data.finance} />
      <HealthStrip engine={data.engine} health={data.health} />
      <div className="grid gap-6 lg:grid-cols-2">
        <AttentionList data={data} />
        <AccountsByType overview={data.overview} />
      </div>
    </>
  );
}
