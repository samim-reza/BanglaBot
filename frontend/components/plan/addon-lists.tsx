"use client";

/** Active add-ons (with where to set them up) and add-ons that are requested rather than bought. */

import Link from "next/link";
import { ArrowRight, Puzzle, Send } from "lucide-react";

import { SectionCard, usd } from "@/components/portal/kit";
import { RequestControls, addonIcon, latestRequest, pendingRequest, useAddonActions, useAddonShop } from "@/components/portal/plan-section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { PlanView } from "@/services/api";

/** Where an active add-on is set up. */
const MANAGE_HREF: Record<string, string> = {
  web_chat: "/channels#web-chat",
  whatsapp: "/channels#whatsapp",
  messenger: "/channels#messenger",
  instagram: "/channels#instagram",
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

export function ActiveAddons({ plan }: { plan: PlanView }) {
  const rows = plan.addons.filter((addon) => addon.quantity > 0);
  if (!rows.length) return null;
  return (
    <SectionCard id="active" icon={Puzzle} title="Active add-ons">
      <ul className="divide-y divide-border rounded-md border border-border">
        {rows.map((addon) => (
          <li key={addon.key} id={`active-${addon.key}`} className="flex scroll-mt-24 flex-wrap items-center gap-3 p-3">
            <AddonIcon addonKey={addon.key} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {addon.name}
                {addon.stackable && addon.quantity > 1 && <span className="ml-1.5 tabular-nums text-muted-foreground">×{addon.quantity}</span>}
              </p>
              <p className="text-xs tabular-nums text-muted-foreground">
                {addon.quantity > 1 ? `${usd(addon.price * addon.quantity)}${addon.period === "once" ? " once" : " / mo"}` : addon.price_label}
              </p>
            </div>
            {MANAGE_HREF[addon.key] && (
              <Button asChild variant="outline" size="sm">
                <Link href={MANAGE_HREF[addon.key]}>
                  Manage
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Link>
              </Button>
            )}
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

/** Add-ons the account may ask for but can't buy at checkout (services, special terms). */
export function RequestAddons({ buyable }: { buyable: Set<string> }) {
  const { shop, setShop } = useAddonShop();
  const actions = useAddonActions(setShop);
  if (!shop) return null;
  const owned = shop.entitlements.addons;
  const items = shop.catalog.filter((item) => shop.available.includes(item.key) && !buyable.has(item.key) && (item.stackable || !owned[item.key]));
  const pending = shop.catalog.filter((item) => pendingRequest(shop, item.key) && !items.includes(item));
  const shown = [...items, ...pending];
  if (!shown.length) return null;
  return (
    <SectionCard id="request" icon={Send} title="On request" info="We confirm these with you and switch them on. No card needed.">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((item) => {
          const open = pendingRequest(shop, item.key);
          const latest = latestRequest(shop, item.key);
          const declined = !open && latest?.status === "declined" ? latest.admin_note.trim() : "";
          return (
            <Card key={item.key} id={item.key} className="flex scroll-mt-24 flex-col gap-3 p-4">
              <div className="flex items-start gap-3">
                <AddonIcon addonKey={item.key} />
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold leading-snug">{item.name}</h4>
                  <p className="text-[13px] font-semibold tabular-nums text-primary-dark dark:text-primary">{item.price_label}</p>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">{item.summary}</p>
              {declined && <p className="text-xs text-muted-foreground">Declined: {declined}</p>}
              <div className="mt-auto pt-1">
                <RequestControls item={item} pending={open} actions={actions} />
              </div>
            </Card>
          );
        })}
      </div>
    </SectionCard>
  );
}
