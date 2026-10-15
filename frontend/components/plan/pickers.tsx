"use client";

/** Shared by the Plan page and the signup wizard: billing period, tier cards, add-on quantities. */

import Link from "next/link";
import { Check, Minus, Plus } from "lucide-react";

import { usd } from "@/components/portal/kit";
import { cn } from "@/lib/utils";
import type { BillingInterval, CatalogAddon, Tier } from "@/services/api";

/** Add-ons that can be bought with `tier` (not already included in it, offered for its product). */
export function addonsFor(addons: CatalogAddon[], tier: Tier | undefined): CatalogAddon[] {
  if (!tier) return [];
  return addons
    .filter((addon) => addon.visible !== false)
    .filter((addon) => !addon.products?.length || addon.products.includes(tier.product))
    .filter((addon) => !(addon.channel && tier.channels.includes(addon.channel as Tier["channels"][number])) && !(addon.feature && tier.includes.includes(addon.feature)))
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0));
}

export function tierPrice(tier: Tier, interval: BillingInterval): number {
  return interval === "year" ? tier.price_year || tier.price_month * 10 : tier.price_month;
}

export function IntervalToggle({ value, onChange }: { value: BillingInterval; onChange: (value: BillingInterval) => void }) {
  return (
    <div role="radiogroup" aria-label="Billing period" className="inline-flex rounded-full border border-border bg-card p-1">
      {(["month", "year"] as BillingInterval[]).map((key) => {
        const active = value === key;
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(key)}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {key === "month" ? "Monthly" : "Yearly"}
            {key === "year" && <span className={cn("rounded-full px-2 py-0.5 text-[11px]", active ? "bg-white/20" : "bg-accent text-accent-foreground")}>2 months free</span>}
          </button>
        );
      })}
    </div>
  );
}

function allowance(tier: Tier): string {
  const parts = [
    tier.included_minutes ? `${tier.included_minutes.toLocaleString("en-US")} min` : "",
    tier.included_chats ? `${tier.included_chats.toLocaleString("en-US")} chats` : "",
    tier.included_sms ? `${tier.included_sms.toLocaleString("en-US")} texts` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

export function TierCards({ tiers, value, interval, current, onChange }: { tiers: Tier[]; value: string; interval: BillingInterval; current?: string; onChange: (key: string) => void }) {
  return (
    <div role="radiogroup" aria-label="Plan" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {tiers.map((tier) => {
        const selected = tier.key === value;
        const body = (
          <>
            <span className="flex items-center justify-between gap-2">
              <span className="font-semibold">{tier.name}</span>
              {current === tier.key ? (
                <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">Current</span>
              ) : tier.highlight ? (
                <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-semibold text-primary-foreground">Popular</span>
              ) : null}
            </span>
            <span className="mt-1 block text-lg font-bold tabular-nums">
              {tier.checkout ? (tierPrice(tier, interval) ? usd(tierPrice(tier, interval)) : "Free") : "Custom"}
              {tier.checkout && tierPrice(tier, interval) > 0 && <span className="text-xs font-medium text-muted-foreground"> / {interval === "year" ? "year" : "mo"}</span>}
            </span>
            {tier.tagline && <span className="mt-1 block text-xs text-muted-foreground">{tier.tagline}</span>}
            {allowance(tier) && <span className="mt-2 block text-xs tabular-nums text-muted-foreground">{allowance(tier)}</span>}
          </>
        );
        if (!tier.checkout) {
          return (
            <Link key={tier.key} href={`/contact?plan=${tier.key}`} className="block rounded-lg border border-dashed border-border bg-card p-4 text-left text-sm transition hover:border-primary">
              {body}
              <span className="mt-2 block text-xs font-semibold text-primary-dark dark:text-primary">Talk to sales</span>
            </Link>
          );
        }
        return (
          <button
            key={tier.key}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(tier.key)}
            className={cn(
              "relative rounded-lg border bg-card p-4 text-left text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              selected ? "border-primary ring-1 ring-primary" : "border-border hover:border-primary/60",
            )}
          >
            {body}
            {selected && <Check className="absolute bottom-3 right-3 h-4 w-4 text-primary" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}

function Stepper({ value, max, label, onChange }: { value: number; max: number; label: string; onChange: (value: number) => void }) {
  const step = "inline-flex h-full w-8 items-center justify-center text-muted-foreground transition hover:text-foreground disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <div role="group" aria-label={label} className="inline-flex h-8 items-center rounded-md border border-input bg-card">
      <button type="button" className={cn(step, "rounded-l-md")} aria-label="Fewer" disabled={value <= 0} onClick={() => onChange(Math.max(0, value - 1))}>
        <Minus className="h-3.5 w-3.5" aria-hidden />
      </button>
      <span className="w-7 text-center text-sm font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button type="button" className={cn(step, "rounded-r-md")} aria-label="More" disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))}>
        <Plus className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}

export function AddonPicker({ addons, value, owned = {}, onChange }: { addons: CatalogAddon[]; value: Record<string, number>; owned?: Record<string, number>; onChange: (next: Record<string, number>) => void }) {
  if (!addons.length) return <p className="text-sm text-muted-foreground">No add-ons for this plan.</p>;
  const set = (key: string, quantity: number) => onChange({ ...value, [key]: quantity });
  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {addons.map((addon) => {
        const quantity = value[addon.key] ?? 0;
        const boughtOnce = addon.period === "once" && (owned[addon.key] ?? 0) > 0;
        return (
          <li key={addon.key} id={addon.key} className="flex scroll-mt-24 flex-wrap items-center gap-3 p-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{addon.name}</p>
              <p className="text-xs text-muted-foreground">
                <span className="font-semibold tabular-nums text-foreground">{addon.price_label}</span>
                {addon.summary && ` · ${addon.summary}`}
              </p>
            </div>
            {boughtOnce ? (
              <span className="text-xs font-semibold text-muted-foreground">Owned</span>
            ) : addon.stackable ? (
              <Stepper value={quantity} max={addon.max_quantity || 10} label={`How many: ${addon.name}`} onChange={(next) => set(addon.key, next)} />
            ) : (
              <label className="inline-flex items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={quantity > 0} onChange={(e) => set(addon.key, e.target.checked ? 1 : 0)} />
                Add
              </label>
            )}
          </li>
        );
      })}
    </ul>
  );
}
