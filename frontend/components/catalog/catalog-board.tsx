"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CirclePlus, Download, Search, Upload } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { catalogApi, formatApiError, type CatalogItem, type CatalogKindSpec } from "@/services/api";

import { CatalogTable } from "./catalog-table";
import { downloadText } from "./columns";
import { ImportPanel } from "./import-panel";
import { ItemDialog } from "./item-dialog";

/**
 * One catalog kind: list, search, add / edit, Offered switch, delete, CSV template + import.
 * `multi` = the vertical has several kinds: the page shows the header and kind tabs, the
 * actions sit in a toolbar here, and API calls name the kind. Single-kind accounts send
 * exactly what they always have (no `?kind=`).
 */
export function CatalogBoard({ spec, primary, multi = false }: { spec: CatalogKindSpec; primary: boolean; multi?: boolean }) {
  const toast = useAppToast();
  const { merchant } = useWorkspace();
  const singular = t(spec.label, "Item");
  const plural = t(spec.label_plural, "Catalog");
  const fields = spec.fields;
  const kind = multi ? spec.kind : undefined;

  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState<{ item: CatalogItem | null } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await catalogApi.list(kind);
      // The API filters by kind; keep the guard so a tab never shows another kind's items.
      setItems(kind ? rows.filter((row) => row.kind === kind) : rows);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, `Could not load your ${plural.toLowerCase()}.`));
    } finally {
      setLoading(false);
    }
  }, [kind, plural]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) =>
      [item.name, ...Object.values(item.data ?? {}).map((value) => (Array.isArray(value) ? value.join(" ") : String(value ?? "")))]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [items, query]);

  const openNew = () => setEditing({ item: null });
  const openEdit = (item: CatalogItem) => setEditing({ item });

  const toggleActive = async (item: CatalogItem) => {
    const next = !item.active;
    setBusyId(item.id);
    setItems((current) => current.map((row) => (row.id === item.id ? { ...row, active: next } : row)));
    try {
      const updated = await catalogApi.update(item.id, { active: next });
      setItems((current) => current.map((row) => (row.id === item.id ? updated : row)));
    } catch (err) {
      setItems((current) => current.map((row) => (row.id === item.id ? { ...row, active: item.active } : row)));
      toast.error(formatApiError(err, "Could not change that item."));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (item: CatalogItem) => {
    if (!window.confirm(`Delete ${item.name}? Your agent stops offering it right away.`)) return;
    setBusyId(item.id);
    try {
      await catalogApi.remove(item.id);
      setItems((current) => current.filter((row) => row.id !== item.id));
      toast.success(`${item.name} deleted.`);
    } catch (err) {
      toast.error(formatApiError(err, `Could not delete ${item.name}.`));
    } finally {
      setBusyId(null);
    }
  };

  const downloadTemplate = async () => {
    setDownloading(true);
    try {
      downloadText(await catalogApi.templateCsv(kind), primary ? "catalog-template.csv" : `${spec.kind}-template.csv`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not download the template."));
    } finally {
      setDownloading(false);
    }
  };

  const activeCount = items.filter((item) => item.active).length;

  const actions = (
    <>
      <Button variant="outline" onClick={() => void downloadTemplate()} disabled={downloading}>
        <Download className="h-4 w-4" aria-hidden="true" />
        {downloading ? "Preparing…" : "Download template"}
      </Button>
      <Button variant="outline" onClick={() => setImportOpen((open) => !open)} aria-expanded={importOpen}>
        <Upload className="h-4 w-4" aria-hidden="true" />
        Import CSV
      </Button>
      <Button onClick={openNew}>
        <CirclePlus className="h-4 w-4" aria-hidden="true" />
        Add {singular.toLowerCase()}
      </Button>
    </>
  );

  return (
    <div className="space-y-6">
      {multi ? (
        <div className="flex flex-wrap items-center justify-end gap-2">{actions}</div>
      ) : (
        <PageHeader title={plural} subtitle="Your agent only offers what's listed here." actions={actions} />
      )}
      <ApiError message={error} />

      {importOpen && <ImportPanel plural={plural.toLowerCase()} kind={kind} onDone={() => void load()} onClose={() => setImportOpen(false)} />}

      {loading ? (
        <div className="space-y-2 rounded-lg border bg-card p-4" role="status" aria-label={`Loading ${plural.toLowerCase()}`}>
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded-md bg-secondary" />
          ))}
        </div>
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={`No ${plural.toLowerCase()} yet`}>
            <Button className="mt-2" onClick={openNew}>
              <CirclePlus className="h-4 w-4" aria-hidden="true" />
              Add {singular.toLowerCase()}
            </Button>
          </EmptyState>
        )
      ) : (
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              {items.length} {items.length === 1 ? singular.toLowerCase() : plural.toLowerCase()} · {activeCount} offered
            </p>
            {items.length > 5 && (
              <div className="relative sm:w-72">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <Input
                  type="search"
                  className="pl-9"
                  aria-label={`Search ${plural.toLowerCase()}`}
                  placeholder={`Search ${plural.toLowerCase()}`}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            )}
          </div>
          {visible.length === 0 ? (
            <EmptyState title="Nothing matches">Try a different search.</EmptyState>
          ) : (
            <CatalogTable
              items={visible}
              fields={fields}
              kind={spec.kind}
              currency={merchant.currency}
              busyId={busyId}
              onEdit={openEdit}
              onToggle={(item) => void toggleActive(item)}
              onRemove={(item) => void remove(item)}
            />
          )}
        </div>
      )}

      {editing && (
        <ItemDialog
          item={editing.item}
          fields={fields}
          singular={singular}
          kind={kind}
          timezone={merchant.timezone}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      )}
    </div>
  );
}
