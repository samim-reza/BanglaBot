"use client";

/** Plan & add-ons: the current tier and usage, changing it (checkout), add-ons on request, billing history. */

import { useMemo } from "react";
import { CircleCheck, RefreshCw, X } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { ActiveAddons, RequestAddons } from "@/components/plan/addon-lists";
import { BillingHistory } from "@/components/plan/billing-history";
import { ChangePlan } from "@/components/plan/change-plan";
import { CurrentPlan } from "@/components/plan/current-plan";
import { addonsFor } from "@/components/plan/pickers";
import { usePlan } from "@/components/plan/use-plan";
import { useHashTarget } from "@/components/portal/plan-section";
import { Button } from "@/components/ui/button";

export default function PlanPage() {
  const { plan, catalog, error, returned, dismissReturned, reload } = usePlan();
  useHashTarget(Boolean(plan && catalog));
  // Add-ons sold at checkout with some tier; the rest go through "On request".
  const buyable = useMemo(
    () => new Set((catalog?.plans ?? []).flatMap((tier) => (tier.checkout ? addonsFor(catalog?.addons ?? [], tier).map((addon) => addon.key) : []))),
    [catalog],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="Plan & add-ons" subtitle="What you pay for and what you use." />
      {returned && (
        <div role="status" className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm">
          <span className="flex items-center gap-2">
            <CircleCheck className="h-4 w-4 text-primary" aria-hidden />
            Payment received — your plan updates in a moment.
          </span>
          <button type="button" aria-label="Dismiss" className="rounded p-1 text-muted-foreground hover:text-foreground" onClick={dismissReturned}>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {plan ? (
        <>
          <CurrentPlan plan={plan} onChanged={reload} />
          <ActiveAddons plan={plan} />
          {catalog && <ChangePlan key={`${plan.tier.key}:${plan.subscription?.id ?? ""}`} plan={plan} catalog={catalog} onChanged={reload} />}
          <RequestAddons buyable={buyable} />
          <BillingHistory refreshKey={plan.subscription?.id ?? plan.tier.key} />
        </>
      ) : error ? (
        <div className="space-y-3">
          <ApiError message={error} />
          <Button type="button" variant="outline" size="sm" onClick={() => void reload()}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Try again
          </Button>
        </div>
      ) : (
        <div className="space-y-4" aria-busy="true" aria-label="Loading plan">
          <div className="h-48 animate-pulse rounded-lg bg-secondary" />
          <div className="h-72 animate-pulse rounded-lg bg-secondary" />
        </div>
      )}
    </div>
  );
}
