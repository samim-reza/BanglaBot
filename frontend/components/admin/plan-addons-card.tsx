"use client";

import { useMemo, useState } from "react";
import { Check, Globe, Info, MessageCircle, MessagesSquare, Minus, Phone } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { HoverInfo } from "@/components/ui/hover-info";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  adminApi,
  formatApiError,
  type AddonCategory,
  type AddonItem,
  type AdminAddonRequest,
  type ChannelKey,
  type Entitlements,
  type Limits,
  type Plan,
} from "@/services/api";

import { AddonRequestRow } from "./addon-requests";
import { Pill } from "./badges";
import { MiniSwitch } from "./form-bits";
import { planPrice } from "./use-admin-meta";

/** Most of a stackable add-on one account can hold (backend MAX_QUANTITY). */
const MAX_QTY = 50;

export const CHANNEL_LABELS: Record<ChannelKey, string> = {
  voice: "Voice",
  web_chat: "Website chat",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
};

const CHANNELS: { key: ChannelKey; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "voice", icon: Phone },
  { key: "web_chat", icon: Globe },
  { key: "whatsapp", icon: MessageCircle },
  { key: "messenger", icon: MessagesSquare },
];

const GROUPS: { key: AddonCategory; label: string }[] = [
  { key: "channel", label: "Channels" },
  { key: "capacity", label: "Capacity" },
  { key: "feature", label: "Features" },
  { key: "service", label: "Services" },
];

const LIMITS: { key: keyof Limits; label: string }[] = [
  { key: "minutes", label: "Minutes" },
  { key: "chats", label: "Chats" },
  { key: "sms", label: "Texts" },
  { key: "numbers", label: "Numbers" },
];

type Quantities = Record<string, number>;

const usd = (value: number) => `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;

/** Only real holdings, keys sorted — for comparing and saving. */
function cleaned(quantities: Quantities): Quantities {
  return Object.fromEntries(
    Object.entries(quantities)
      .filter(([, qty]) => qty > 0)
      .sort(([a], [b]) => a.localeCompare(b)),
  );
}

/** The plan already gives this add-on's channel or feature. */
function includedByPlan(addon: AddonItem, plan: Plan): boolean {
  if (addon.channel && plan.channels?.includes(addon.channel)) return true;
  return Boolean(addon.feature && plan.includes?.includes(addon.feature));
}

/**
 * The account's plan, channels and monthly limits, its pending add-on
 * requests, and an editor for its add-ons (Save replaces the whole set).
 */
export function PlanAddonsCard({
  merchantId,
  plan,
  entitlements,
  requests,
  catalog,
  catalogError,
  onChanged,
}: {
  merchantId: string;
  plan: Plan;
  entitlements: Entitlements;
  requests: AdminAddonRequest[];
  catalog: AddonItem[] | null;
  catalogError?: string | null;
  onChanged: () => void;
}) {
  const saved = useMemo(() => cleaned(entitlements.addons ?? {}), [entitlements.addons]);
  const pending = requests.filter((request) => request.status === "pending");
  const past = requests.filter((request) => request.status !== "pending");
  const active = new Set(entitlements.channels ?? []);

  return (
    <Card className="lg:col-span-3">
      <CardHeader>
        <CardTitle>Plan & add-ons</CardTitle>
        <CardDescription>
          {plan.name} · {planPrice(plan)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-5 md:grid-cols-2">
          <div>
            <SubHeading>Channels</SubHeading>
            <ul className="mt-2 flex flex-wrap gap-2">
              {CHANNELS.map(({ key, icon: Icon }) => {
                const on = active.has(key);
                return (
                  <li key={key}>
                    <Pill tone={on ? "green" : "neutral"} className={cn(!on && "opacity-70")}>
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      {CHANNEL_LABELS[key]}
                      {on ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Minus className="h-3.5 w-3.5" aria-hidden="true" />}
                      <span className="sr-only">{on ? " (on)" : " (off)"}</span>
                    </Pill>
                  </li>
                );
              })}
            </ul>
          </div>
          <div>
            <SubHeading>Monthly limits</SubHeading>
            <dl className="mt-2 grid grid-cols-4 gap-2">
              {LIMITS.map(({ key, label }) => {
                const value = entitlements.limits?.[key];
                return (
                  <div key={key} className="rounded-md border border-border px-2.5 py-2">
                    <dt className="text-[11.5px] font-medium text-muted-foreground">{label}</dt>
                    <dd className="mt-0.5 font-semibold tabular-nums">{value === null || value === undefined ? "∞" : value.toLocaleString("en-US")}</dd>
                  </div>
                );
              })}
            </dl>
          </div>
        </div>

        {pending.length > 0 && (
          <section
            aria-label="Pending requests"
            className="rounded-md border border-[#fcd34d] bg-[#fef3c7]/50 px-3 pt-3 dark:border-amber-500/30 dark:bg-amber-500/5"
          >
            <h4 className="flex items-center gap-2 text-sm font-semibold">
              Requests
              <Pill tone="amber">{pending.length}</Pill>
            </h4>
            <div className="divide-y divide-[#fcd34d]/70 dark:divide-amber-500/20">
              {pending.map((request) => (
                <AddonRequestRow key={request.id} request={request} onDecided={onChanged} />
              ))}
            </div>
          </section>
        )}

        {catalog ? (
          // Re-mounts (fresh draft) whenever the saved set changes, e.g. after an approval.
          <AddonEditor key={JSON.stringify(saved)} merchantId={merchantId} plan={plan} catalog={catalog} saved={saved} onSaved={onChanged} />
        ) : (
          <p className={cn("text-sm", catalogError ? "text-destructive" : "text-muted-foreground")} role="status">
            {catalogError ?? "Loading add-ons…"}
          </p>
        )}

        {past.length > 0 && (
          <details className="group rounded-md border border-border px-3">
            <summary className="cursor-pointer list-none py-2.5 text-sm font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
              Past requests ({past.length})
            </summary>
            <div className="divide-y divide-border border-t border-border">
              {past.map((request) => (
                <AddonRequestRow key={request.id} request={request} onDecided={onChanged} />
              ))}
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</p>;
}

function AddonEditor({
  merchantId,
  plan,
  catalog,
  saved,
  onSaved,
}: {
  merchantId: string;
  plan: Plan;
  catalog: AddonItem[];
  saved: Quantities;
  onSaved: () => void;
}) {
  const toast = useAppToast();
  const [draft, setDraft] = useState<Quantities>(saved);
  const [busy, setBusy] = useState(false);

  const next = cleaned(draft);
  const dirty = JSON.stringify(next) !== JSON.stringify(saved);
  const byKey = new Map(catalog.map((addon) => [addon.key, addon]));
  let monthly = 0;
  let once = 0;
  for (const [key, qty] of Object.entries(next)) {
    const addon = byKey.get(key);
    if (!addon) continue;
    if (addon.period === "once") once += addon.price * qty;
    else monthly += addon.price * qty;
  }

  const setQty = (key: string, qty: number) => setDraft((current) => ({ ...current, [key]: qty }));

  const save = async () => {
    setBusy(true);
    try {
      await adminApi.setAddons(merchantId, next);
      toast.success("Add-ons saved.");
      onSaved();
    } catch (err) {
      toast.error(formatApiError(err, "Could not save the add-ons."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {GROUPS.map((group) => {
          const items = catalog.filter((addon) => addon.category === group.key);
          if (!items.length) return null;
          return (
            <section key={group.key} aria-label={group.label}>
              <SubHeading>{group.label}</SubHeading>
              <ul className="mt-2 divide-y divide-border rounded-md border border-border">
                {items.map((addon) => (
                  <AddonRow key={addon.key} addon={addon} plan={plan} qty={draft[addon.key] ?? 0} onChange={(qty) => setQty(addon.key, qty)} disabled={busy} />
                ))}
              </ul>
            </section>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <p className="text-sm">
          <span className="text-muted-foreground">Add-ons </span>
          <span className="font-semibold tabular-nums">{usd(monthly)} / mo</span>
          {once > 0 && <span className="tabular-nums text-muted-foreground"> + {usd(once)} once</span>}
        </p>
        <div className="flex gap-2">
          {dirty && (
            <Button variant="ghost" onClick={() => setDraft(saved)} disabled={busy}>
              Reset
            </Button>
          )}
          <Button onClick={() => void save()} disabled={!dirty || busy}>
            {busy ? "Saving…" : "Save add-ons"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function AddonRow({
  addon,
  plan,
  qty,
  onChange,
  disabled,
}: {
  addon: AddonItem;
  plan: Plan;
  qty: number;
  onChange: (qty: number) => void;
  disabled: boolean;
}) {
  const included = includedByPlan(addon, plan);
  const products = addon.products ?? [];
  const otherProduct = products.length > 0 && !products.includes(plan.product);

  let control: React.ReactNode;
  if (qty === 0 && included) {
    control = <Pill tone="teal">Included</Pill>;
  } else if (qty === 0 && otherProduct) {
    control = <span className="text-xs text-muted-foreground">{products.includes("voice") ? "Voice only" : "Chat only"}</span>;
  } else if (addon.stackable) {
    control = (
      <Input
        type="number"
        inputMode="numeric"
        min={0}
        max={MAX_QTY}
        step={1}
        value={qty}
        disabled={disabled}
        aria-label={`${addon.name} quantity`}
        onChange={(event) => {
          const value = Math.floor(Number(event.target.value));
          onChange(Number.isFinite(value) ? Math.max(0, Math.min(MAX_QTY, value)) : 0);
        }}
        className="h-8 w-[4.5rem] text-right tabular-nums"
      />
    );
  } else {
    control = <MiniSwitch checked={qty > 0} onChange={(on) => onChange(on ? 1 : 0)} label={addon.name} disabled={disabled} />;
  }

  return (
    <li className="flex items-center gap-3 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <span className="truncate">{addon.name}</span>
          <HoverInfo trigger={<Info className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />} width={240}>
            <span className="text-xs text-foreground">{addon.summary}</span>
          </HoverInfo>
          <span className="sr-only">{addon.summary}</span>
          {included && qty > 0 && <Pill tone="neutral">In plan</Pill>}
        </div>
        <p className="text-xs tabular-nums text-muted-foreground">
          {addon.price_label}
          {addon.stackable ? " each" : ""}
        </p>
      </div>
      {control}
    </li>
  );
}
