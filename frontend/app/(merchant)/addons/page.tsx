"use client";

/** The add-on shop: the plan, what is active, and what can be requested (the platform admin switches it on). */

import Link from "next/link";
import { ArrowRight, Puzzle, RefreshCw } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { SectionCard, usd } from "@/components/portal/kit";
import {
  PlanSection,
  RequestControls,
  addonIcon,
  latestRequest,
  pendingRequest,
  useAddonActions,
  useAddonShop,
  useHashTarget,
  type AddonActions,
} from "@/components/portal/plan-section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { AddonCategory, AddonItem, AddonShop } from "@/services/api";

const CATEGORIES: { key: AddonCategory; label: string }[] = [
  { key: "channel", label: "Channels" },
  { key: "capacity", label: "More capacity" },
  { key: "feature", label: "Features" },
  { key: "service", label: "Services" },
];

/** Where an active add-on is set up. */
const MANAGE_HREF: Record<string, string> = {
  web_chat: "/channels#web-chat",
  whatsapp: "/channels#whatsapp",
  messenger: "/channels#messenger",
  sms: "/settings?tab=notifications",
  google_calendar: "/settings?tab=calendar",
};

function AddonIcon({ addonKey }: { addonKey: string }) {
  const Icon = addonIcon(addonKey);
  return (
    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
      <Icon className="h-4 w-4" aria-hidden />
    </span>
  );
}

function priceFor(item: AddonItem, quantity: number): string {
  if (quantity <= 1) return item.price_label;
  return `${usd(item.price * quantity)}${item.period === "once" ? " once" : " / mo"}`;
}

/** Add-ons on sale: what the account may request, minus single add-ons it already has. */
function forSale(shop: AddonShop): AddonItem[] {
  const owned = shop.entitlements.addons;
  return shop.catalog.filter((item) => shop.available.includes(item.key) && (item.stackable || !owned[item.key]));
}

function ActiveAddons({ shop, onSale, highlight }: { shop: AddonShop; onSale: Set<string>; highlight: string | null }) {
  const rows = shop.catalog.filter((item) => (shop.entitlements.addons[item.key] ?? 0) > 0);
  return (
    <SectionCard id="active" icon={Puzzle} title="Active">
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No add-ons yet.</p>
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {rows.map((item) => {
            const quantity = shop.entitlements.addons[item.key] ?? 1;
            const href = MANAGE_HREF[item.key];
            // A card further down already carries the plain key as its anchor.
            const id = onSale.has(item.key) ? `active-${item.key}` : item.key;
            return (
              <li key={item.key} id={id} className={cn("flex scroll-mt-24 flex-wrap items-center gap-3 p-3", highlight === id && "bg-accent/40")}>
                <AddonIcon addonKey={item.key} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    {item.name}
                    {item.stackable && quantity > 1 && <span className="ml-1.5 tabular-nums text-muted-foreground">×{quantity}</span>}
                  </p>
                  <p className="text-xs tabular-nums text-muted-foreground">{priceFor(item, quantity)}</p>
                </div>
                {href && (
                  <Button asChild variant="outline" size="sm">
                    <Link href={href}>
                      Manage
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </Link>
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

function AddonCard({ item, shop, actions, highlighted }: { item: AddonItem; shop: AddonShop; actions: AddonActions; highlighted: boolean }) {
  const owned = shop.entitlements.addons[item.key] ?? 0;
  const pending = pendingRequest(shop, item.key);
  const latest = latestRequest(shop, item.key);
  const declined = !pending && latest?.status === "declined" && latest.admin_note.trim() ? latest.admin_note.trim() : "";
  return (
    <Card id={item.key} className={cn("flex scroll-mt-24 flex-col gap-3 p-4 transition-shadow", highlighted && "ring-2 ring-primary")}>
      <div className="flex items-start gap-3">
        <AddonIcon addonKey={item.key} />
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold leading-snug">{item.name}</h4>
          <p className="text-[13px] font-semibold tabular-nums text-primary-dark">{item.price_label}</p>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{item.summary}</p>
      {item.stackable && owned > 0 && <p className="text-xs text-muted-foreground">You have ×{owned}</p>}
      {declined && <p className="text-xs text-muted-foreground">Declined: {declined}</p>}
      <div className="mt-auto pt-1">
        <RequestControls item={item} pending={pending} actions={actions} />
      </div>
    </Card>
  );
}

function AddMore({ shop, items, actions, highlight }: { shop: AddonShop; items: AddonItem[]; actions: AddonActions; highlight: string | null }) {
  return (
    <section aria-labelledby="add-more-title" className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="add-more-title" className="text-lg font-semibold">
          Add more
        </h2>
        <p className="text-sm text-muted-foreground">No card needed — we confirm and switch it on.</p>
      </div>
      {items.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">You have every add-on.</p>
      ) : (
        CATEGORIES.map((category) => {
          const group = items.filter((item) => item.category === category.key);
          if (group.length === 0) return null;
          return (
            <div key={category.key} className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{category.label}</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {group.map((item) => (
                  <AddonCard key={item.key} item={item} shop={shop} actions={actions} highlighted={highlight === item.key} />
                ))}
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}

export default function AddonsPage() {
  const { shop, setShop, error, reload } = useAddonShop();
  const actions = useAddonActions(setShop);
  const highlight = useHashTarget(shop !== null);
  const items = shop ? forSale(shop) : [];
  const onSale = new Set(items.map((item) => item.key));

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="Add-ons" subtitle="Extras on top of your plan." />
      <PlanSection />
      {shop ? (
        <>
          <ActiveAddons shop={shop} onSale={onSale} highlight={highlight} />
          <AddMore shop={shop} items={items} actions={actions} highlight={highlight} />
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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label="Loading add-ons">
          {[0, 1, 2].map((index) => (
            <div key={index} className="h-40 animate-pulse rounded-lg border border-border bg-surface" />
          ))}
        </div>
      )}
    </div>
  );
}
