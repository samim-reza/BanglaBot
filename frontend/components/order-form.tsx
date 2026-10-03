"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { CircleAlert } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { SchemaFields, validateValues, type FormValues } from "@/components/schema-form";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { catalogApi, formatApiError, type CatalogItem, type FieldSpec, type Order, type OrderUpdate } from "@/services/api";

/** A record field's current value: from its column, or from `details` for vertical-only fields. */
export function recordFieldValue(order: Order, spec: FieldSpec): unknown {
  if (spec.column) {
    const raw = (order as unknown as Record<string, unknown>)[spec.column];
    if (spec.type === "money" || spec.type === "number") {
      if (raw === null || raw === undefined || raw === "") return raw;
      const numeric = Number(raw);
      return Number.isNaN(numeric) ? raw : numeric;
    }
    return raw;
  }
  return order.details?.[spec.key];
}

/** Prefill values for the record form from a saved record. */
export function recordToFormValues(order: Order, specs: FieldSpec[]): FormValues {
  const out: FormValues = {};
  for (const spec of specs) {
    const value = recordFieldValue(order, spec);
    if (value !== null && value !== undefined) out[spec.key] = value;
  }
  return out;
}

/** `{catalog_item_id: name}` from records the API already resolved. */
export function catalogNamesOf(orders: Order[]): Record<string, string> {
  const names: Record<string, string> = {};
  for (const order of orders) {
    if (order.catalog_item_id && order.catalog_item_name) names[order.catalog_item_id] = order.catalog_item_name;
  }
  return names;
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
}

function sameValue(a: unknown, b: unknown): boolean {
  if (isEmpty(a) && isEmpty(b)) return true;
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Record columns the API stores as non-null text: they can be changed but not emptied. */
const NOT_NULL_TEXT_COLUMNS = new Set(["customer_name", "customer_phone", "order_ref", "address", "items_summary", "notes"]);

/**
 * PATCH body with only the fields that changed. Cleared optional fields are sent
 * as `null` (the API drops them); text columns that cannot be emptied are left
 * out and reported in `kept` so the caller can tell the user.
 */
export function recordUpdatePayload(specs: FieldSpec[], initial: FormValues, values: FormValues): { payload: OrderUpdate; kept: string[] } {
  const payload: OrderUpdate = {};
  const kept: string[] = [];
  for (const spec of specs) {
    const before = initial[spec.key];
    const after = values[spec.key];
    if (sameValue(before, after)) continue;
    if (isEmpty(after)) {
      if (spec.column && NOT_NULL_TEXT_COLUMNS.has(spec.column)) {
        kept.push(t(spec.label));
        continue;
      }
      payload[spec.key] = null;
    } else {
      payload[spec.key] = after;
    }
  }
  return { payload, kept };
}

/**
 * The record form ("New appointment", editing a lead, …), rendered from the
 * account's vertical field specs. Catalog fields (doctor, listing, service) are
 * filled from the account's catalog; date-times use the account's time zone.
 */
export function RecordForm({
  initial,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: FormValues;
  submitLabel: string;
  busy: boolean;
  onSubmit: (values: FormValues) => void;
  onCancel?: () => void;
}) {
  const { vertical, merchant } = useWorkspace();
  const specs = vertical.record_fields;
  const needsCatalog = Boolean(vertical.catalog_kind) && specs.some((spec) => spec.type === "catalog");
  const catalogRequired = specs.some((spec) => spec.type === "catalog" && spec.required);
  const hasDateTime = specs.some((spec) => spec.type === "datetime");
  const [values, setValues] = useState<FormValues>(initial);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[] | null>(needsCatalog ? null : []);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  useEffect(() => {
    if (!needsCatalog) return;
    let cancelled = false;
    catalogApi
      .list()
      .then((items) => {
        if (!cancelled) setCatalog(items);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setCatalog([]);
          setCatalogError(formatApiError(err, `Could not load your ${t(vertical.catalog_label_plural, "catalog").toLowerCase()}.`));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [needsCatalog, vertical.catalog_label_plural]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const problem = validateValues(specs, values);
    setError(problem);
    if (problem) return;
    onSubmit(values);
  };

  const catalogPlural = t(vertical.catalog_label_plural, "catalog items").toLowerCase();

  return (
    <form className="space-y-5" onSubmit={submit} noValidate>
      <ApiError message={catalogError} />
      {needsCatalog && catalog !== null && catalog.length === 0 && !catalogError && (
        <div className="flex items-start gap-2.5 rounded-md border border-border bg-surface p-3 text-sm">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-muted-foreground">
            No {catalogPlural} yet{catalogRequired ? " — this form needs one" : ""}.{" "}
            <Link href="/catalog" className="font-medium text-primary-dark underline-offset-2 hover:underline">
              Add {catalogPlural}
            </Link>
          </p>
        </div>
      )}
      <SchemaFields
        specs={specs}
        values={values}
        onChange={(next) => {
          setValues(next);
          if (error) setError(null);
        }}
        catalog={catalog ?? []}
        timezone={merchant.timezone}
        disabled={busy}
      />
      {needsCatalog && catalog === null && <p className="text-xs text-muted-foreground">Loading {catalogPlural}…</p>}
      {error && (
        <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
          <CircleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        )}
        <span className="text-xs text-muted-foreground sm:ml-auto">
          * required{hasDateTime ? ` · times in ${merchant.timezone}` : ""}
        </span>
      </div>
    </form>
  );
}
