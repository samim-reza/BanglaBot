"use client";

import { Suspense } from "react";

import { Segments } from "@/components/agent-flow/bits";
import { FinanceAccountsTable } from "@/components/admin/finance/accounts-table";
import { CapsCard } from "@/components/admin/finance/caps-card";
import { ExportButtons } from "@/components/admin/finance/export-buttons";
import { FinanceOverviewTab } from "@/components/admin/finance/finance-overview";
import { monthLabel } from "@/components/admin/finance/labels";
import { PricebookEditor } from "@/components/admin/finance/pricebook-editor";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { FilterBar, LoadingRows } from "@/components/admin/states";
import { useUrlFilters } from "@/components/admin/url-filters";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Input } from "@/components/ui/input";

const KEYS = ["tab", "month"] as const;
const TABS = [
  { value: "overview", label: "Overview" },
  { value: "accounts", label: "Accounts" },
  { value: "prices", label: "Price book" },
  { value: "caps", label: "Caps" },
] as const;
type Tab = (typeof TABS)[number]["value"];

const thisMonth = () => new Date().toISOString().slice(0, 7);

export default function AdminFinancePage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading finance…" />}>
      <FinanceView />
    </Suspense>
  );
}

function FinanceView() {
  const { can, loading } = useAdminMe();
  const [f, setFilters] = useUrlFilters(KEYS);
  const tab: Tab = TABS.some((t) => t.value === f.tab) ? (f.tab as Tab) : "overview";
  const month = /^\d{4}-\d{2}$/.test(f.month) ? f.month : thisMonth();
  const monthScoped = tab === "overview" || tab === "accounts";

  if (loading) return <LoadingRows label="Loading finance…" />;
  if (!can("finance")) return <EmptyState title="Finance and superadmin only" />;

  return (
    <>
      <PageHeader title="Finance" subtitle={monthScoped ? `${monthLabel(month)} · USD · UTC` : "USD"} />
      <FilterBar label="Finance view">
        <Segments label="Section" value={tab} options={[...TABS]} onChange={(next) => setFilters({ tab: next === "overview" ? null : next })} />
        {monthScoped && (
          <>
            <Input
              type="month"
              className="h-9 sm:w-44"
              aria-label="Month"
              value={month}
              max={thisMonth()}
              onChange={(e) => setFilters({ month: e.target.value === thisMonth() ? null : e.target.value })}
            />
            <span className="flex gap-2 sm:ml-auto">
              <ExportButtons month={month} />
            </span>
          </>
        )}
      </FilterBar>
      {tab === "overview" && <FinanceOverviewTab month={month} />}
      {tab === "accounts" && <FinanceAccountsTable month={month} />}
      {tab === "prices" && <PricebookEditor />}
      {tab === "caps" && <CapsCard />}
    </>
  );
}
