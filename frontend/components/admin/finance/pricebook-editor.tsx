"use client";

import { useMemo, useState } from "react";
import { Save } from "lucide-react";

import { FilterBar, LoadingRows } from "@/components/admin/states";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate } from "@/lib/format";

import { categoryLabel } from "./labels";
import { PriceRow } from "./price-row";
import { usePricebook } from "./use-pricebook";

/** Unit prices per provider + SKU. Changes save as a new version effective from a chosen date. */
export function PricebookEditor() {
  const pb = usePricebook();
  const toast = useAppToast();
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [effective, setEffective] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");

  const categories = useMemo(() => [...new Set(pb.book?.prices.map((p) => p.category) ?? [])].sort(), [pb.book]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (pb.book?.prices ?? []).filter((p) => (!category || p.category === category) && (!q || `${p.provider} ${p.sku}`.toLowerCase().includes(q)));
  }, [pb.book, category, query]);

  if (!pb.book) return pb.error ? <ApiError message={pb.error} /> : <LoadingRows label="Loading the price book…" rows={6} />;

  const save = async () => {
    if (await pb.save(effective, note.trim())) {
      setNote("");
      toast.success("New price version saved.");
    }
  };

  return (
    <div className="space-y-4">
      <FilterBar label="Filter prices">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">In force on</span>
          <Input type="date" className="h-9 w-40" value={pb.at} onChange={(e) => e.target.value && pb.setAt(e.target.value)} aria-label="Show the book in force on" />
        </label>
        <Select className="h-9 sm:w-44" aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {categoryLabel(c)}
            </option>
          ))}
        </Select>
        <Input className="h-9 sm:w-56" placeholder="Search provider or SKU" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search prices" />
        <span className="text-xs text-muted-foreground sm:ml-auto">
          Version {pb.book.version} · from {formatDate(pb.book.effective_from)}
        </span>
      </FilterBar>
      <ApiError message={pb.error} />
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Unit</TableHead>
              <TableHead className="text-right" title="What we pay (USD)">
                Cost $
              </TableHead>
              <TableHead className="text-right" title="Shadow price used for 'would cost' on free tiers / cache">
                List $
              </TableHead>
              <TableHead title="Billed at $0 (free tier)">Free</TableHead>
              <TableHead className="text-right" title="Billing increment in seconds (telephony)">
                Incr. s
              </TableHead>
              <TableHead>Note</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((price) => (
              <PriceRow key={price.key} price={price} edit={pb.edits[price.key]} onEdit={(patch) => pb.edit(price.key, patch)} disabled={pb.saving} />
            ))}
          </TableBody>
        </Table>
      </div>
      {pb.dirty && (
        <div className="sticky bottom-3 z-30 flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-3 shadow-lg">
          <span className="text-sm font-medium">{Object.keys(pb.edits).length} changed</span>
          <label className="flex flex-col gap-1 text-xs font-semibold text-muted-foreground">
            Effective from
            <Input type="date" className="h-8 w-40" value={effective} onChange={(e) => setEffective(e.target.value)} />
          </label>
          <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-xs font-semibold text-muted-foreground">
            Note
            <Input className="h-8" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Deepgram price change" />
          </label>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={pb.discard} disabled={pb.saving}>
              Discard
            </Button>
            <Button size="sm" onClick={() => void save()} disabled={pb.saving}>
              <Save className="h-3.5 w-3.5" />
              {pb.saving ? "Saving…" : "Save version"}
            </Button>
          </div>
        </div>
      )}
      <details className="rounded-lg border border-border bg-card p-4 text-sm">
        <summary className="cursor-pointer font-semibold">Versions ({pb.book.versions.length})</summary>
        <ul className="mt-3 divide-y divide-border">
          {[...pb.book.versions].reverse().map((v) => (
            <li key={`${v.effective_from}-${v.created_at}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <button type="button" className="font-medium text-primary hover:underline" onClick={() => pb.setAt(v.effective_from)}>
                From {formatDate(v.effective_from)}
              </button>
              <span className="text-xs text-muted-foreground">
                {Object.keys(v.prices).length} prices{v.note ? ` · ${v.note}` : ""}
                {v.created_at ? ` · ${formatDate(v.created_at)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
