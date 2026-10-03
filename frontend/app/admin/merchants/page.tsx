"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, LogIn, Pencil, Plus, Search, Trash2, X } from "lucide-react";

import { ActiveBadge, Pill } from "@/components/admin/badges";
import { OpenPortalDialog, DeleteMerchantDialog } from "@/components/admin/merchant-actions";
import { MerchantCreateDialog } from "@/components/admin/merchant-create-dialog";
import { MerchantEditDrawer } from "@/components/admin/merchant-edit-drawer";
import { FilterBar, LoadingRows } from "@/components/admin/states";
import { useAdminMerchants, useAdminMeta, planName, regionOf, verticalName } from "@/components/admin/use-admin-meta";
import { useUrlFilters } from "@/components/admin/url-filters";
import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { languageLabel } from "@/lib/format";
import type { Merchant } from "@/services/api";

const FILTER_KEYS = ["vertical", "create"] as const;

export default function AdminAccountsPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading accounts…" />}>
      <AccountsView />
    </Suspense>
  );
}

function AccountsView() {
  const router = useRouter();
  const { meta, error: metaError } = useAdminMeta();
  const { merchants, loading, error, reload } = useAdminMerchants();
  const [filters, setFilters] = useUrlFilters(FILTER_KEYS);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Merchant | null>(null);
  const [opening, setOpening] = useState<Merchant | null>(null);
  const [deleting, setDeleting] = useState<Merchant | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  // Deep link from the overview: /admin/merchants?create=1 opens the form once.
  useEffect(() => {
    if (filters.create) {
      setCreateOpen(true);
      setFilters({ create: null });
    }
  }, [filters.create, setFilters]);

  const vertical = filters.vertical;
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return merchants.filter((merchant) => {
      if (vertical && merchant.vertical !== vertical) return false;
      if (!needle) return true;
      return [merchant.business_name, merchant.username, merchant.owner_name, merchant.email, merchant.phone, merchant.inbound_number]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [merchants, query, vertical]);

  const filtered = Boolean(query.trim() || vertical);

  return (
    <>
      <PageHeader
        title="Accounts"
        subtitle="Every business on the platform, the agent it runs and the number it answers."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Create account
          </Button>
        }
      />
      <ApiError message={error ?? metaError} />

      <FilterBar label="Filter accounts">
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, username, email, number…"
            aria-label="Search accounts"
            className="pl-9"
          />
        </div>
        <Select
          className="sm:w-56"
          aria-label="Business type"
          value={vertical}
          onChange={(event) => setFilters({ vertical: event.target.value })}
        >
          <option value="">All business types</option>
          {meta?.verticals.map((spec) => (
            <option key={spec.key} value={spec.key}>
              {verticalName(meta, spec.key)}
            </option>
          ))}
        </Select>
        {filtered && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQuery("");
              setFilters({ vertical: null });
            }}
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        )}
        {!loading && (
          <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
            {filtered
              ? `${visible.length} of ${merchants.length} accounts`
              : `${merchants.length} account${merchants.length === 1 ? "" : "s"}`}
          </p>
        )}
      </FilterBar>

      {loading ? (
        <LoadingRows label="Loading accounts…" />
      ) : merchants.length === 0 ? (
        error ? null : (
          <EmptyState title="No accounts yet">
            <p>Create the first account to get a business answering calls.</p>
            <Button className="mt-4" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Create account
            </Button>
          </EmptyState>
        )
      ) : visible.length === 0 ? (
        <EmptyState title="No accounts match">Try a different search or business type.</EmptyState>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Business</TableHead>
                <TableHead className="hidden 2xl:table-cell">Username</TableHead>
                <TableHead>Business type</TableHead>
                <TableHead>Region</TableHead>
                <TableHead className="hidden 2xl:table-cell">Language</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Inbound number</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((merchant) => {
                const region = regionOf(meta, merchant.region);
                return (
                  <TableRow key={merchant.id}>
                    <TableCell className="min-w-[12rem]">
                      <Link href={`/admin/merchants/${merchant.id}`} className="font-semibold hover:text-primary hover:underline">
                        {merchant.business_name}
                      </Link>
                      <div className="text-xs text-muted-foreground">
                        {merchant.owner_name}
                        {/* Username has its own column on very wide screens only. */}
                        <span className="font-mono 2xl:hidden">
                          {merchant.owner_name ? " · " : ""}
                          {merchant.username}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs 2xl:table-cell">{merchant.username}</TableCell>
                    <TableCell className="whitespace-nowrap">{verticalName(meta, merchant.vertical)}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {region?.label ?? merchant.region}
                      <span className="ml-1 text-xs text-muted-foreground">{merchant.region}</span>
                    </TableCell>
                    <TableCell className="hidden whitespace-nowrap 2xl:table-cell">{languageLabel(merchant.language)}</TableCell>
                    <TableCell>
                      <Pill tone="teal">{planName(meta, merchant.plan)}</Pill>
                    </TableCell>
                    <TableCell className="whitespace-nowrap font-mono text-xs">
                      {merchant.inbound_number || <span className="font-sans text-muted-foreground">Not set</span>}
                    </TableCell>
                    <TableCell>
                      <ActiveBadge active={merchant.active} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button asChild size="icon" variant="ghost" className="h-8 w-8" title="View account">
                          <Link href={`/admin/merchants/${merchant.id}`} aria-label={`View ${merchant.business_name}`}>
                            <Eye className="h-4 w-4" />
                          </Link>
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          title="Edit account"
                          aria-label={`Edit ${merchant.business_name}`}
                          onClick={() => setEditing(merchant)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          title={merchant.active ? "Open portal as owner" : "Activate the account to open its portal"}
                          aria-label={`Open portal of ${merchant.business_name}`}
                          disabled={!merchant.active}
                          onClick={() => setOpening(merchant)}
                        >
                          <LogIn className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          title="Delete account"
                          aria-label={`Delete ${merchant.business_name}`}
                          onClick={() => setDeleting(merchant)}
                        >
                          <Trash2 className="h-4 w-4" />
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

      <MerchantCreateDialog
        open={createOpen}
        meta={meta}
        onClose={() => setCreateOpen(false)}
        onCreated={(merchant) => {
          setCreateOpen(false);
          router.push(`/admin/merchants/${merchant.id}`);
        }}
      />
      <MerchantEditDrawer
        merchant={editing}
        meta={meta}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          void reload();
        }}
      />
      <OpenPortalDialog merchant={opening} onClose={() => setOpening(null)} />
      <DeleteMerchantDialog
        merchant={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={() => {
          setDeleting(null);
          void reload();
        }}
      />
    </>
  );
}
