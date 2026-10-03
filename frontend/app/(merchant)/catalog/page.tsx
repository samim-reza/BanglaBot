"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { CircleAlert, CirclePlus, Download, FileSpreadsheet, Pencil, Search, Trash2, Upload, X } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, PageHeader } from "@/components/page-header";
import { SchemaFields, compactValues, defaultValues, validateValues, type FormValues } from "@/components/schema-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { displayValue, money, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { catalogApi, formatApiError, type CatalogImportResult, type CatalogItem, type FieldSpec } from "@/services/api";

type Column = { key: string; label: string; numeric?: boolean; render: (item: CatalogItem) => string };

/** The 2–4 fields that identify an item at a glance, per catalog kind (generic fallback otherwise). */
const PREFERRED: Record<string, string[]> = {
  doctor: ["specialty", "days", "hours", "fee"],
  property: ["listing_type", "property_type", "location", "price"],
  service: ["category", "visit_charge", "price_range", "duration"],
};

function catalogColumns(fields: FieldSpec[], kind: string, currency: string): Column[] {
  const byKey = new Map(fields.map((spec) => [spec.key, spec]));
  const fieldColumn = (spec: FieldSpec): Column => ({
    key: spec.key,
    label: t(spec.label),
    numeric: spec.type === "money" || spec.type === "number",
    render: (item) => displayValue(spec, item.data?.[spec.key], { currency }),
  });
  const columns: Column[] = [];
  for (const key of PREFERRED[kind] ?? []) {
    if (key === "hours" && byKey.has("start_time") && byKey.has("end_time")) {
      columns.push({
        key,
        label: "Hours",
        render: (item) => {
          const start = item.data?.start_time;
          const end = item.data?.end_time;
          return start || end ? `${start || "?"}–${end || "?"}` : "—";
        },
      });
    } else if (key === "price_range" && byKey.has("price_from")) {
      columns.push({
        key,
        label: "Usual price",
        numeric: true,
        render: (item) => {
          const from = item.data?.price_from;
          const to = item.data?.price_to;
          if (from === undefined || from === null || from === "") return "—";
          return to !== undefined && to !== null && to !== "" ? `${money(from, currency)}–${money(to, currency)}` : `from ${money(from, currency)}`;
        },
      });
    } else {
      const spec = byKey.get(key);
      if (spec) columns.push(fieldColumn(spec));
    }
  }
  if (!columns.length) {
    return fields
      .filter((spec) => spec.key !== "name" && spec.type !== "textarea" && spec.type !== "list")
      .slice(0, 3)
      .map(fieldColumn);
  }
  return columns.slice(0, 4);
}

function downloadText(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Minimal accessible modal: Escape / backdrop close, focus moves in and back out. */
function Dialog({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const first = panelRef.current?.querySelector<HTMLElement>("input, select, textarea, button:not([data-dialog-close])");
    first?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (event.key === "Tab" && panelRef.current) {
        const focusable = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])"),
        );
        if (!focusable.length) return;
        const firstEl = focusable[0];
        const lastEl = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === firstEl) {
          event.preventDefault();
          lastEl.focus();
        } else if (!event.shiftKey && document.activeElement === lastEl) {
          event.preventDefault();
          firstEl.focus();
        }
      }
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
      opener?.focus?.();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <button type="button" tabIndex={-1} aria-label="Close" className="absolute inset-0 bg-foreground/40" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="catalog-dialog-title"
        className="relative flex max-h-[92vh] w-full flex-col rounded-t-xl border border-border bg-card shadow-xl sm:max-w-2xl sm:rounded-xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
          <div>
            <h2 id="catalog-dialog-title" className="text-base font-semibold">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
          </div>
          <button
            type="button"
            data-dialog-close
            aria-label="Close"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ActiveSwitch({ checked, disabled, label, onChange }: { checked: boolean; disabled?: boolean; label: string; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        checked ? "bg-primary" : "bg-border",
      )}
    >
      <span className={cn("inline-block h-4 w-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  );
}

function ImportPanel({ plural, onDone, onClose }: { plural: string; onDone: () => void; onClose: () => void }) {
  const toast = useAppToast();
  const [csv, setCsv] = useState("");
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CatalogImportResult | null>(null);
  const [fileName, setFileName] = useState("");

  const readFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      setCsv(await file.text());
      setFileName(file.name);
      setResult(null);
      setError(null);
    } catch {
      setError("Could not read that file.");
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!csv.trim()) {
      setError("Choose a CSV file or paste its contents first.");
      return;
    }
    if (replace && !window.confirm(`Replace all your current ${plural} with this file? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await catalogApi.importCsv(csv, replace);
      setResult(next);
      toast.success(`${next.created} imported${next.skipped ? `, ${next.skipped} skipped` : ""}.`);
      onDone();
    } catch (err) {
      setError(formatApiError(err, "Could not import the CSV."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-primary" aria-hidden="true" />
            Import from CSV
          </CardTitle>
          <CardDescription>The first row names the columns (use the template). Each further row becomes one item.</CardDescription>
        </div>
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" aria-label="Close import" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-md border border-border bg-card px-4 py-2 text-sm font-semibold hover:bg-secondary focus-within:ring-2 focus-within:ring-ring">
              <Upload className="h-4 w-4" aria-hidden="true" />
              Choose file
              <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(event) => void readFile(event.target.files?.[0])} />
            </label>
            <span className="truncate text-sm text-muted-foreground">{fileName || "…or paste the CSV below"}</span>
          </div>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-[13.5px] font-semibold text-muted-foreground">CSV contents</span>
            <Textarea
              rows={6}
              value={csv}
              onChange={(event) => {
                setCsv(event.target.value);
                setResult(null);
              }}
              className="font-mono text-xs"
              placeholder={"name,…\nFirst item,…"}
              spellCheck={false}
            />
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-primary" checked={replace} onChange={(event) => setReplace(event.target.checked)} />
            <span>
              Replace existing items
              <span className="block text-xs text-muted-foreground">Deletes every current item first. Leave off to add to your list.</span>
            </span>
          </label>
          <ApiError message={error} />
          {result && (
            <div className="rounded-md border border-border bg-surface p-3 text-sm" role="status">
              <p>
                <span className="font-semibold">{result.created}</span> created · <span className="font-semibold">{result.skipped}</span> skipped
              </p>
              {result.errors.length > 0 && (
                <ul className="mt-2 max-h-40 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs text-destructive">
                  {result.errors.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={busy}>
              <Upload className="h-4 w-4" aria-hidden="true" />
              {busy ? "Importing…" : "Import"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

type Editing = { item: CatalogItem | null; values: FormValues };

export default function CatalogPage() {
  const toast = useAppToast();
  const { vertical, merchant } = useWorkspace();
  const hasCatalog = Boolean(vertical.catalog_kind);
  const singular = t(vertical.catalog_label, "Item");
  const plural = t(vertical.catalog_label_plural, "Catalog");
  const fields = vertical.catalog_fields;

  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(hasCatalog);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    if (!hasCatalog) return;
    try {
      setItems(await catalogApi.list());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, `Could not load your ${plural.toLowerCase()}.`));
    } finally {
      setLoading(false);
    }
  }, [hasCatalog, plural]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo(() => catalogColumns(fields, vertical.catalog_kind, merchant.currency), [fields, vertical.catalog_kind, merchant.currency]);
  // A short secondary line under the name: the first plain text field not already shown as a column.
  const subtitleSpec = useMemo(
    () => fields.find((spec) => spec.key !== "name" && spec.type === "text" && !columns.some((column) => column.key === spec.key)),
    [fields, columns],
  );
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

  if (!hasCatalog) {
    return (
      <div className="space-y-6">
        <PageHeader title="Catalog" subtitle="What your agent can offer callers." />
        <EmptyState title="Your agent doesn't use a catalog">
          <p>
            A {t(vertical.label).toLowerCase()} agent works from your {t(vertical.record_label_plural, "records").toLowerCase()}: it reads each{" "}
            {t(vertical.record_label, "record").toLowerCase()}&apos;s details back to the customer, so there is no list of doctors, listings or services to keep here.
          </p>
          <p className="mt-3">
            <Link href="/orders" className="font-medium text-primary-dark hover:underline">
              Go to your {t(vertical.record_label_plural, "records").toLowerCase()}
            </Link>
          </p>
        </EmptyState>
      </div>
    );
  }

  const openNew = () => {
    setFormError(null);
    setEditing({ item: null, values: defaultValues(fields) });
  };

  const openEdit = (item: CatalogItem) => {
    setFormError(null);
    setEditing({ item, values: { ...(item.data ?? {}), name: item.name } });
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    const problem = validateValues(fields, editing.values);
    if (problem) {
      setFormError(problem);
      return;
    }
    const { name, ...rest } = editing.values;
    setSaving(true);
    setFormError(null);
    try {
      if (editing.item) {
        // Cleared optional fields are sent as "" so the API removes them.
        await catalogApi.update(editing.item.id, { name: String(name ?? "").trim(), data: rest });
        toast.success(`${singular} updated.`);
      } else {
        await catalogApi.create({ name: String(name ?? "").trim(), data: compactValues(rest) });
        toast.success(`${singular} added.`);
      }
      setEditing(null);
      await load();
    } catch (err) {
      setFormError(formatApiError(err, `Could not save the ${singular.toLowerCase()}.`));
    } finally {
      setSaving(false);
    }
  };

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
      downloadText(await catalogApi.templateCsv(), "catalog-template.csv");
    } catch (err) {
      toast.error(formatApiError(err, "Could not download the template."));
    } finally {
      setDownloading(false);
    }
  };

  const activeCount = items.filter((item) => item.active).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title={plural}
        subtitle={`Your agent only offers what is on this list. Switch a ${singular.toLowerCase()} off to hide it from callers without deleting it.`}
        actions={
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
        }
      />
      <ApiError message={error} />

      {importOpen && <ImportPanel plural={plural.toLowerCase()} onDone={() => void load()} onClose={() => setImportOpen(false)} />}

      {loading ? (
        <div className="space-y-2 rounded-lg border bg-card p-4" role="status" aria-label={`Loading ${plural.toLowerCase()}`}>
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded-md bg-secondary" />
          ))}
        </div>
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={`No ${plural.toLowerCase()} yet`}>
            <p>Your agent can only offer and book what is listed here. Add them one by one, or import a CSV.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <Button onClick={openNew}>
                <CirclePlus className="h-4 w-4" aria-hidden="true" />
                Add {singular.toLowerCase()}
              </Button>
              <Button variant="outline" onClick={() => setImportOpen(true)}>
                <Upload className="h-4 w-4" aria-hidden="true" />
                Import CSV
              </Button>
            </div>
          </EmptyState>
        )
      ) : (
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              {items.length} {items.length === 1 ? singular.toLowerCase() : plural.toLowerCase()} · {activeCount} offered to callers
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
            <div className="overflow-hidden rounded-lg border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t(fields.find((spec) => spec.key === "name")?.label, "Name")}</TableHead>
                    {columns.map((column) => (
                      <TableHead key={column.key} className={column.numeric ? "text-right" : undefined}>
                        {column.label}
                      </TableHead>
                    ))}
                    <TableHead>Offered</TableHead>
                    <TableHead className="text-right">
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.map((item) => {
                    const subtitle = subtitleSpec ? item.data?.[subtitleSpec.key] : null;
                    return (
                      <TableRow key={item.id} className={cn(!item.active && "text-muted-foreground")}>
                        <TableCell className="min-w-44">
                          <button type="button" className="text-left font-medium hover:underline" onClick={() => openEdit(item)}>
                            {item.name}
                          </button>
                          {subtitle ? <div className="text-xs text-muted-foreground">{String(subtitle)}</div> : null}
                        </TableCell>
                        {columns.map((column) => {
                          const text = column.render(item);
                          return (
                            <TableCell
                              key={column.key}
                              className={cn(column.numeric ? "whitespace-nowrap text-right tabular-nums" : "max-w-[14rem] truncate")}
                              title={text}
                            >
                              {text}
                            </TableCell>
                          );
                        })}
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <ActiveSwitch
                              checked={item.active}
                              disabled={busyId === item.id}
                              label={`Offer ${item.name} to callers`}
                              onChange={() => void toggleActive(item)}
                            />
                            <span className="text-xs text-muted-foreground">{item.active ? "On" : "Off"}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button size="sm" variant="ghost" onClick={() => openEdit(item)} aria-label={`Edit ${item.name}`}>
                              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                              <span className="hidden sm:inline">Edit</span>
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-destructive hover:bg-destructive/10"
                              onClick={() => void remove(item)}
                              disabled={busyId === item.id}
                              aria-label={`Delete ${item.name}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
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
        </div>
      )}

      {editing && (
        <Dialog
          title={editing.item ? `Edit ${editing.item.name}` : `Add ${singular.toLowerCase()}`}
          description="Your agent reads these details to callers and books from them."
          onClose={() => (saving ? undefined : setEditing(null))}
        >
          <form className="flex min-h-0 flex-1 flex-col" onSubmit={save} noValidate>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
              <SchemaFields
                specs={fields}
                values={editing.values}
                onChange={(values) => {
                  setEditing((current) => (current ? { ...current, values } : current));
                  if (formError) setFormError(null);
                }}
                timezone={merchant.timezone}
                disabled={saving}
              />
            </div>
            <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              {formError ? (
                <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
                  <CircleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {formError}
                </p>
              ) : (
                <span className="text-xs text-muted-foreground">* required</span>
              )}
              <div className="flex gap-2 sm:justify-end">
                <Button type="button" variant="ghost" onClick={() => setEditing(null)} disabled={saving}>
                  Cancel
                </Button>
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving…" : editing.item ? "Save changes" : `Add ${singular.toLowerCase()}`}
                </Button>
              </div>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
