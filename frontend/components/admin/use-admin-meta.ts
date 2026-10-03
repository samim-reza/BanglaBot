"use client";

import { useCallback, useEffect, useState } from "react";

import { t } from "@/lib/vertical";
import {
  adminApi,
  formatApiError,
  publicApi,
  type AddonItem,
  type AdminMeta,
  type Merchant,
  type Plan,
  type Region,
  type VerticalSpec,
} from "@/services/api";

/**
 * Form choices (business engines, regions, plans, languages) are static per
 * deploy, so one request serves every admin screen for the life of the tab.
 * A failed request is not cached, so the next screen retries.
 */
let metaPromise: Promise<AdminMeta> | null = null;

function loadMeta(): Promise<AdminMeta> {
  if (!metaPromise) {
    metaPromise = adminApi.meta().catch((err) => {
      metaPromise = null;
      throw err;
    });
  }
  return metaPromise;
}

export function useAdminMeta() {
  const [meta, setMeta] = useState<AdminMeta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadMeta()
      .then((data) => {
        if (!cancelled) {
          setMeta(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(formatApiError(err, "Could not load the account options."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { meta, error };
}

/** The add-on catalog (static per deploy, like meta), from the public catalog endpoint. */
let addonsPromise: Promise<AddonItem[]> | null = null;

function loadAddons(): Promise<AddonItem[]> {
  if (!addonsPromise) {
    addonsPromise = publicApi
      .catalog()
      .then((catalog) => catalog.addons ?? [])
      .catch((err) => {
        addonsPromise = null;
        throw err;
      });
  }
  return addonsPromise;
}

export function useAddonCatalog() {
  const [addons, setAddons] = useState<AddonItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadAddons()
      .then((data) => !cancelled && setAddons(data))
      .catch((err) => !cancelled && setError(formatApiError(err, "Could not load the add-on catalog.")));
    return () => {
      cancelled = true;
    };
  }, []);

  return { addons, error };
}

/** Every account, for filters and look-ups. Reloads on each mount (accounts change). */
export function useAdminMerchants() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setMerchants(await adminApi.merchants());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load accounts."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { merchants, loading, error, reload };
}

export function verticalOf(meta: AdminMeta | null, key: string | null | undefined): VerticalSpec | null {
  return meta?.verticals.find((spec) => spec.key === key) ?? null;
}

export function verticalName(meta: AdminMeta | null, key: string | null | undefined): string {
  const spec = verticalOf(meta, key);
  if (spec) return t(spec.label, spec.key);
  return key ? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "—";
}

export function regionOf(meta: AdminMeta | null, code: string | null | undefined): Region | null {
  return meta?.regions.find((region) => region.code === code) ?? null;
}

export function planOf(meta: AdminMeta | null, key: string | null | undefined): Plan | null {
  return meta?.plans.find((plan) => plan.key === key) ?? null;
}

export function planName(meta: AdminMeta | null, key: string | null | undefined): string {
  return planOf(meta, key)?.name ?? (key ? key.charAt(0).toUpperCase() + key.slice(1) : "—");
}

/** "$149/mo" — plans are priced in USD. */
export function planPrice(plan: Plan): string {
  if (!plan.price_month) return "Free";
  return `$${plan.price_month.toLocaleString("en-US")}/mo`;
}
