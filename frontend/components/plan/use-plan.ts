"use client";

/** The owner's plan view + the tiers / add-ons on sale for this business type, and the checkout return. */

import { useCallback, useEffect, useState } from "react";

import { useWorkspace } from "@/lib/workspace";
import { billingApi, formatApiError, signupApi, type PlanView, type SignupCatalog } from "@/services/api";

export function usePlan() {
  const { merchant, refresh } = useWorkspace();
  const [plan, setPlan] = useState<PlanView | null>(null);
  const [catalog, setCatalog] = useState<SignupCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Back from checkout (`/plan?reference=…`). */
  const [returned, setReturned] = useState(false);

  const load = useCallback(async () => {
    try {
      const [view, offer] = await Promise.all([billingApi.get(), signupApi.catalog(merchant.vertical).catch(() => null)]);
      setPlan(view);
      if (offer) setCatalog(offer);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load your plan."));
    }
  }, [merchant.vertical]);

  /** After a change: the plan view and the shell's usage / entitlements. */
  const reload = useCallback(async () => {
    await Promise.all([load(), refresh()]);
  }, [load, refresh]);

  useEffect(() => {
    void load();
  }, [load]);

  // The payment confirms asynchronously: look again a couple of times, then drop the query.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.get("reference")) return;
    setReturned(true);
    params.delete("reference");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
    const timers = [1500, 5000].map((delay) => window.setTimeout(() => void reload(), delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [reload]);

  return { plan, catalog, error, returned, dismissReturned: () => setReturned(false), reload };
}

export type PlanState = ReturnType<typeof usePlan>;
