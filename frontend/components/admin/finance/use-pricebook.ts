"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { formatApiError } from "@/services/api";
import { financeApi, type Price, type PriceOverride, type Pricebook } from "@/services/api/admin/finance";

export type PriceEdit = Partial<Pick<Price, "unit_cost" | "list_price" | "free_tier" | "increment_secs" | "note">>;

const today = () => new Date().toISOString().slice(0, 10);

/** The price book in force on `at`, with edits that save as a new version from a chosen date. */
export function usePricebook() {
  const [at, setAt] = useState(today);
  const [book, setBook] = useState<Pricebook | null>(null);
  const [edits, setEdits] = useState<Record<string, PriceEdit>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (day: string) => {
    try {
      setBook(await financeApi.pricebook(day));
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load the price book."));
    }
  }, []);

  useEffect(() => {
    void load(at);
  }, [at, load]);

  const byKey = useMemo(() => new Map(book?.prices.map((p) => [p.key, p]) ?? []), [book]);

  /** Record an edit; an edit back to the book's value is dropped. */
  const edit = useCallback(
    (key: string, patch: PriceEdit) => {
      setEdits((current) => {
        const base = byKey.get(key);
        const next: PriceEdit = { ...current[key], ...patch };
        for (const field of Object.keys(next) as (keyof PriceEdit)[]) {
          if (base && String(base[field]) === String(next[field])) delete next[field];
        }
        const out = { ...current };
        if (Object.keys(next).length) out[key] = next;
        else delete out[key];
        return out;
      });
    },
    [byKey],
  );

  const discard = useCallback(() => setEdits({}), []);

  const save = useCallback(
    async (effectiveFrom: string, note: string): Promise<boolean> => {
      const prices: PriceOverride[] = Object.entries(edits).flatMap(([key, change]) => {
        const base = byKey.get(key);
        return base ? [{ provider: base.provider, sku: base.sku, ...change }] : [];
      });
      if (!prices.length) return false;
      setSaving(true);
      try {
        const saved = await financeApi.savePricebook({ effective_from: effectiveFrom || undefined, note, prices });
        setEdits({});
        setAt(saved.at);
        setBook(saved);
        setError(null);
        return true;
      } catch (err) {
        setError(formatApiError(err, "Could not save the price book."));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [edits, byKey],
  );

  return { at, setAt, book, edits, edit, discard, save, saving, error, dirty: Object.keys(edits).length > 0 };
}
