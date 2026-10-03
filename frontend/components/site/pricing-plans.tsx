"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ENTERPRISE, PLANS, TRIAL, TRIAL_HREF, annualMonthly, annualTotal, usd, type SitePlan } from "@/lib/site-content";
import { cn } from "@/lib/utils";

type Billing = "monthly" | "annual";

function BillingToggle({ value, onChange }: { value: Billing; onChange: (value: Billing) => void }) {
  const options: { key: Billing; label: string; hint?: string }[] = [
    { key: "monthly", label: "Monthly" },
    { key: "annual", label: "Annual", hint: "2 months free" },
  ];
  return (
    <div role="group" aria-label="Billing period" className="inline-flex rounded-full border border-border bg-card p-1">
      {options.map((option) => {
        const active = value === option.key;
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.key)}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
            {option.hint && (
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                  active ? "bg-white/20 text-primary-foreground" : "bg-accent text-accent-foreground",
                )}
              >
                {option.hint}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function Price({ monthly, billing, prefix }: { monthly: number; billing: Billing; prefix?: string }) {
  const shown = billing === "annual" ? annualMonthly(monthly) : monthly;
  return (
    <div>
      <p className="flex items-baseline gap-1">
        {prefix && <span className="mr-1 text-sm font-medium text-muted-foreground">{prefix}</span>}
        <span className="text-4xl font-bold tracking-tight tabular-nums text-foreground">{usd(shown)}</span>
        <span className="text-sm text-muted-foreground">/ month</span>
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {billing === "annual" ? `Billed ${usd(annualTotal(monthly))} yearly` : "Billed monthly · cancel anytime"}
      </p>
    </div>
  );
}

function PlanCard({ plan, billing }: { plan: SitePlan; billing: Billing }) {
  return (
    <li
      className={cn(
        "relative flex flex-col rounded-2xl border bg-card p-6",
        plan.highlight ? "border-primary shadow-[0_24px_60px_-30px_rgb(13_148_136/0.55)] ring-1 ring-primary" : "border-border",
      )}
    >
      {plan.highlight && (
        <span className="absolute -top-3 left-6 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
          Most popular
        </span>
      )}
      <h3 className="text-lg font-semibold text-foreground">{plan.name}</h3>
      <p className="mt-1 min-h-[40px] text-sm text-muted-foreground">{plan.tagline}</p>
      <div className="mt-5">
        <Price monthly={plan.price} billing={billing} />
      </div>
      <Button asChild variant={plan.highlight ? "default" : "outline"} className="mt-6 w-full">
        <Link href={`/contact?plan=${plan.key}`} aria-label={`Start with the ${plan.name} plan`}>
          Start with {plan.name}
        </Link>
      </Button>
      <ul className="mt-6 space-y-2.5 text-sm">
        {plan.features.map((feature) => (
          <li key={feature} className="flex gap-2.5 text-foreground">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
            {feature}
          </li>
        ))}
      </ul>
      <div className="mt-auto pt-6">
        <p className="border-t border-border pt-4 text-xs text-muted-foreground">
          Extra minutes {usd(plan.overage, 2)} each
        </p>
      </div>
    </li>
  );
}

/** Plan cards with a Monthly / Annual toggle (annual = 2 months free). */
export function PricingPlans({ showEnterprise = true }: { showEnterprise?: boolean }) {
  const [billing, setBilling] = useState<Billing>("monthly");
  return (
    <div>
      <div className="flex flex-col items-center gap-3">
        <BillingToggle value={billing} onChange={setBilling} />
        <p className="text-center text-sm text-muted-foreground">
          Not sure yet?{" "}
          <Link href={TRIAL_HREF} className="font-semibold text-primary-dark hover:underline">
            Start a {TRIAL.days}-day free trial
          </Link>{" "}
          with {TRIAL.minutes} call minutes.
        </p>
      </div>

      <ul className="mt-10 grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => (
          <PlanCard key={plan.key} plan={plan} billing={billing} />
        ))}
      </ul>

      {showEnterprise && (
        <div className="mt-6 grid gap-6 rounded-2xl border border-border bg-surface p-6 md:grid-cols-[1fr_1.4fr_auto] md:items-center">
          <div>
            <h3 className="text-lg font-semibold text-foreground">{ENTERPRISE.name}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{ENTERPRISE.tagline}</p>
            <div className="mt-4">
              <Price monthly={ENTERPRISE.priceFrom} billing={billing} prefix="from" />
            </div>
          </div>
          <ul className="grid gap-2.5 text-sm sm:grid-cols-2">
            {ENTERPRISE.features.map((feature) => (
              <li key={feature} className="flex gap-2.5 text-foreground">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                {feature}
              </li>
            ))}
          </ul>
          <Button asChild variant="outline" className="w-full md:w-auto">
            <Link href="/contact?plan=enterprise">
              Talk to sales
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
