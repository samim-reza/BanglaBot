"use client";

/** Wizard step 1: which kind of business (decides the agent, the tiers and the add-ons). */

import { Building2, CalendarCheck, Check, Contact, ShoppingBag, Stethoscope, Wrench, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { SignupCatalog } from "@/services/api";

const ICONS: Record<string, LucideIcon> = {
  clinic: Stethoscope,
  dental: Stethoscope,
  vet: Stethoscope,
  real_estate: Contact,
  home_service: Wrench,
  ecommerce: ShoppingBag,
  restaurant: CalendarCheck,
};

export function StepBusiness({ verticals, value, onChange }: { verticals: SignupCatalog["verticals"]; value: string; onChange: (key: string) => void }) {
  return (
    <div role="radiogroup" aria-label="Business type" className="grid gap-3 sm:grid-cols-2">
      {verticals.map((vertical) => {
        const Icon = ICONS[vertical.key] ?? Building2;
        const selected = vertical.key === value;
        return (
          <button
            key={vertical.key}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(vertical.key)}
            className={cn(
              "relative flex items-start gap-3 rounded-lg border bg-card p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              selected ? "border-primary ring-1 ring-primary" : "border-border hover:border-primary/60",
            )}
          >
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">{t(vertical.label, vertical.key)}</span>
              {t(vertical.description) && <span className="mt-0.5 block text-xs text-muted-foreground">{t(vertical.description)}</span>}
            </span>
            {selected && <Check className="absolute right-3 top-3 h-4 w-4 text-primary" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}
