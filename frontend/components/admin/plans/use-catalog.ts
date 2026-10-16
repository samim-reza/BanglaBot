"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { canon } from "@/components/admin/flow/flow-paths";
import { formatApiError } from "@/services/api";
import { plansApi, type CatalogAddon, type CatalogTier, type PlanCatalog } from "@/services/api/admin/plans";

import { catalogErrors, NO_ERRORS, type CatalogErrors } from "./catalog-errors";

export type CatalogKind = "tiers" | "addons";

const bySort = <T extends { sort: number }>(rows: T[]) => [...rows].sort((a, b) => a.sort - b.sort);
const renumber = <T extends { sort: number }>(rows: T[]) => rows.map((row, i) => ({ ...row, sort: (i + 1) * 10 }));

export const NEW_TIER = (sort: number): CatalogTier => ({
  key: "",
  name: "",
  tagline: "",
  product: "voice",
  price_month: 0,
  price_year: 0,
  overage_per_minute: 0,
  included_minutes: 0,
  included_chats: 0,
  included_sms: 0,
  phone_numbers: 1,
  channels: ["voice"],
  includes: [],
  features: [],
  limits: { max_concurrent_calls: 1, flow_editing: "lines", payments: false, custom_fields: false, api_webhooks: false },
  verticals: [],
  visible: false,
  checkout: true,
  highlight: false,
  trial_days: 0,
  sort,
});

export const NEW_ADDON = (sort: number): CatalogAddon => ({
  key: "",
  name: "",
  category: "capacity",
  price: 0,
  period: "month",
  summary: "",
  stackable: true,
  max_quantity: 10,
  channel: "",
  feature: "",
  grants: { minutes: 100 },
  products: [],
  verticals: [],
  visible: false,
  sort,
});

/** The catalog editor's draft: every tier and add-on, saved as one document. */
export function useCatalog() {
  const [saved, setSaved] = useState<PlanCatalog | null>(null);
  const [tiers, setTiers] = useState<CatalogTier[]>([]);
  const [addons, setAddons] = useState<CatalogAddon[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<CatalogErrors>(NO_ERRORS);
  const [saving, setSaving] = useState(false);

  const install = useCallback((data: PlanCatalog) => {
    setSaved({ ...data, tiers: bySort(data.tiers), addons: bySort(data.addons) });
    setTiers(bySort(data.tiers));
    setAddons(bySort(data.addons));
    setErrors(NO_ERRORS);
  }, []);

  useEffect(() => {
    plansApi
      .catalog()
      .then(install)
      .catch((err) => setLoadError(formatApiError(err, "Could not load the catalog.")));
  }, [install]);

  const savedKeys = useMemo(
    () => ({ tiers: new Set(saved?.tiers.map((row) => row.key)), addons: new Set(saved?.addons.map((row) => row.key)) }),
    [saved],
  );
  const dirty = Boolean(saved) && (canon(tiers) !== canon(saved?.tiers) || canon(addons) !== canon(saved?.addons));

  const updateTier = useCallback((i: number, patch: Partial<CatalogTier>) => setTiers((rows) => rows.map((row, j) => (j === i ? { ...row, ...patch } : row))), []);
  const updateAddon = useCallback((i: number, patch: Partial<CatalogAddon>) => setAddons((rows) => rows.map((row, j) => (j === i ? { ...row, ...patch } : row))), []);

  const move = useCallback((kind: CatalogKind, i: number, step: -1 | 1) => {
    const swap = <T extends { sort: number }>(rows: T[]) => {
      const j = i + step;
      if (j < 0 || j >= rows.length) return rows;
      const next = [...rows];
      [next[i], next[j]] = [next[j], next[i]];
      return renumber(next);
    };
    if (kind === "tiers") setTiers(swap);
    else setAddons(swap);
  }, []);

  const add = useCallback((kind: CatalogKind) => {
    if (kind === "tiers") setTiers((rows) => [...rows, NEW_TIER((rows.length + 1) * 10)]);
    else setAddons((rows) => [...rows, NEW_ADDON((rows.length + 1) * 10)]);
  }, []);

  const remove = useCallback((kind: CatalogKind, i: number) => {
    if (kind === "tiers") setTiers((rows) => rows.filter((_, j) => j !== i));
    else setAddons((rows) => rows.filter((_, j) => j !== i));
  }, []);

  const discard = useCallback(() => saved && install(saved), [saved, install]);

  const save = useCallback(async (): Promise<boolean> => {
    setSaving(true);
    try {
      install(await plansApi.saveCatalog(tiers, addons.map(({ price_label: _label, ...rest }) => rest as CatalogAddon)));
      return true;
    } catch (err) {
      setErrors(catalogErrors(err, formatApiError(err, "Could not save the catalog.")));
      return false;
    } finally {
      setSaving(false);
    }
  }, [tiers, addons, install]);

  return { saved, tiers, addons, savedKeys, loadError, errors, saving, dirty, updateTier, updateAddon, move, add, remove, discard, save };
}

export type CatalogEditor = ReturnType<typeof useCatalog>;
