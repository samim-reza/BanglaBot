"use client";

/** Upgrade / downgrade / buy add-ons: pick a tier, period and add-ons; see the price; pay at checkout. */

import { useMemo, useState } from "react";
import { ArrowUpDown, LoaderCircle } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { SectionCard, usd } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { billingApi, formatApiError, type BillingInterval, type PlanSelection, type PlanView, type SignupCatalog } from "@/services/api";

import { AddonPicker, IntervalToggle, TierCards, addonsFor } from "./pickers";
import { QuoteSummary, useQuote } from "./quote-summary";

function currentSelection(plan: PlanView): PlanSelection {
  const addons: Record<string, number> = {};
  for (const addon of plan.addons) if (addon.period !== "once") addons[addon.key] = addon.quantity;
  return { tier: plan.tier.key, interval: plan.subscription?.interval ?? plan.renewal?.interval ?? "month", addons };
}

export function ChangePlan({ plan, catalog, onChanged }: { plan: PlanView; catalog: SignupCatalog; onChanged: () => Promise<void> }) {
  const toast = useAppToast();
  const tiers = useMemo(() => catalog.plans.filter((tier) => tier.visible !== false).sort((a, b) => a.sort - b.sort), [catalog.plans]);
  const [selection, setSelection] = useState<PlanSelection>(() => currentSelection(plan));
  const [busy, setBusy] = useState(false);
  const tier = tiers.find((item) => item.key === selection.tier) ?? plan.tier;
  const offered = useMemo(() => addonsFor(catalog.addons, tier), [catalog.addons, tier]);
  const owned = useMemo(() => Object.fromEntries(plan.addons.map((addon) => [addon.key, addon.quantity])), [plan.addons]);

  // Only send add-ons this tier can take, with a quantity.
  const sent: PlanSelection = {
    ...selection,
    addons: Object.fromEntries(Object.entries(selection.addons).filter(([key, qty]) => qty > 0 && offered.some((addon) => addon.key === key))),
  };
  const key = JSON.stringify(sent);
  const priced = useQuote(key, (body) => billingApi.quote(JSON.parse(body) as PlanSelection), tier.checkout !== false);
  const change = priced.data?.change ?? null;
  const same = change?.kind === "same";

  const confirm = async () => {
    setBusy(true);
    try {
      const result = await billingApi.change(sent);
      if (result.checkout_url) {
        window.location.assign(result.checkout_url);
        return;
      }
      toast.success(result.change.effective === "period_end" ? "Scheduled for your next period." : "Plan updated.");
      await onChanged();
    } catch (err) {
      toast.error(formatApiError(err, "Could not change your plan."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard id="change" icon={ArrowUpDown} title="Change plan" badge={<IntervalToggle value={selection.interval} onChange={(interval: BillingInterval) => setSelection((s) => ({ ...s, interval }))} />}>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 space-y-5">
          <TierCards tiers={tiers} value={selection.tier} interval={selection.interval} current={plan.tier.key} onChange={(tierKey) => setSelection((s) => ({ ...s, tier: tierKey }))} />
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Add-ons</h3>
            <AddonPicker addons={offered} value={selection.addons} owned={owned} onChange={(addons) => setSelection((s) => ({ ...s, addons }))} />
          </div>
        </div>
        <div className="space-y-3 lg:sticky lg:top-[77px] lg:h-fit">
          <QuoteSummary quote={priced.data?.quote ?? null} change={change} loading={priced.loading} error={priced.error} />
          <Button type="button" className="w-full" disabled={busy || priced.loading || !priced.data || same} onClick={() => void confirm()}>
            {busy && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            {change && change.due_now > 0 ? `Pay ${usd(change.due_now)}` : "Confirm"}
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}
