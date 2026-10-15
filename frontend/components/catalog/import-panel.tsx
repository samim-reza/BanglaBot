"use client";

import { FormEvent, useState } from "react";
import { FileSpreadsheet, Upload, X } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { catalogApi, formatApiError, type CatalogImportResult } from "@/services/api";

/** CSV import for one catalog kind (`kind` is only sent when the vertical has several). */
export function ImportPanel({ plural, kind, onDone, onClose }: { plural: string; kind?: string; onDone: () => void; onClose: () => void }) {
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
      const next = await catalogApi.importCsv(csv, replace, kind);
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
          <CardDescription>One row per item, with the template&apos;s columns.</CardDescription>
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
              <span className="block text-xs text-muted-foreground">Deletes current items first.</span>
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
