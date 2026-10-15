"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { AccountHeader } from "@/components/admin/account/account-header";
import { AccountOverview } from "@/components/admin/account/account-overview";
import { ACCOUNT_TABS, AccountTabs, type AccountTab } from "@/components/admin/account/account-tabs";
import { ProvidersTab } from "@/components/admin/account/providers-tab";
import { useAccount } from "@/components/admin/account/use-account";
import { CallFlowTab } from "@/components/admin/flow/call-flow-tab";
import { DeleteMerchantDialog, OpenPortalDialog } from "@/components/admin/merchant-actions";
import { MerchantEditDrawer } from "@/components/admin/merchant-edit-drawer";
import { LoadingRows } from "@/components/admin/states";
import { useUrlFilters } from "@/components/admin/url-filters";
import { useAddonCatalog, useAdminMeta } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { EmptyState } from "@/components/page-header";
import type { Merchant } from "@/services/api";
import type { ProviderChains } from "@/services/api/admin/flow";

const TAB_KEYS = ["tab"] as const;

export default function AdminAccountDetailPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading account…" rows={6} />}>
      <AccountView />
    </Suspense>
  );
}

function AccountView() {
  const params = useParams<{ id: string }>();
  const id = String(params?.id ?? "");
  const router = useRouter();
  const { meta } = useAdminMeta();
  const { addons: catalog, error: catalogError } = useAddonCatalog();
  const { detail, error, notFound, loading, reload } = useAccount(id);
  const [filters, setFilters] = useUrlFilters(TAB_KEYS);
  const tab: AccountTab = ACCOUNT_TABS.some((item) => item.key === filters.tab) ? (filters.tab as AccountTab) : "overview";
  const [editing, setEditing] = useState(false);
  const [opening, setOpening] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const backLink = (
    <Link href="/admin/merchants" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Accounts
    </Link>
  );

  if (loading) {
    return (
      <>
        {backLink}
        <LoadingRows label="Loading account…" rows={6} />
      </>
    );
  }

  if (notFound || !detail) {
    return (
      <>
        {backLink}
        <ApiError message={error} />
        {notFound && <EmptyState title="Account not found">It may have been deleted.</EmptyState>}
      </>
    );
  }

  const { merchant } = detail;
  // Not in the account payload yet (backend gap); shown when the API starts returning it.
  const providers = (merchant as Merchant & { provider_settings?: Partial<ProviderChains> }).provider_settings;

  return (
    <>
      {backLink}
      <ApiError message={error} />
      <AccountHeader detail={detail} onEdit={() => setEditing(true)} onOpenPortal={() => setOpening(true)} onDelete={() => setDeleting(true)} />
      <AccountTabs value={tab} onChange={(next) => setFilters({ tab: next === "overview" ? null : next })} />

      <div role="tabpanel" id={`account-panel-${tab}`} aria-labelledby={`account-tab-${tab}`}>
        {tab === "overview" && (
          <AccountOverview
            detail={detail}
            meta={meta}
            catalog={catalog}
            catalogError={catalogError}
            onEdit={() => setEditing(true)}
            onChanged={() => void reload()}
          />
        )}
        {tab === "flow" && <CallFlowTab merchantId={merchant.id} />}
        {tab === "providers" && <ProvidersTab merchantId={merchant.id} current={providers} />}
      </div>

      <MerchantEditDrawer
        merchant={editing ? merchant : null}
        meta={meta}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          void reload();
        }}
      />
      <OpenPortalDialog merchant={opening ? merchant : null} onClose={() => setOpening(false)} />
      <DeleteMerchantDialog
        merchant={deleting ? merchant : null}
        onClose={() => setDeleting(false)}
        onDeleted={() => {
          setDeleting(false);
          router.replace("/admin/merchants");
        }}
      />
    </>
  );
}
