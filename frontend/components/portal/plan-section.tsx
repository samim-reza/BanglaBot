"use client";

/** Plan & usage this month, plus the add-on shop helpers shared by the Add-ons and Channels pages. */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Archive,
  ArrowRight,
  CalendarSync,
  Clock,
  CreditCard,
  Handshake,
  Languages,
  LoaderCircle,
  MessageCircle,
  MessageCircleMore,
  MessageSquare,
  Minus,
  PhoneCall,
  Plus,
  Puzzle,
  Smartphone,
  Timer,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionCard, usd, formatNumber } from "@/components/portal/kit";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { addonsApi, formatApiError, type AddonItem, type AddonRequest, type AddonShop, type ChannelKey } from "@/services/api";

// ---------------------------------------------------------------- labels + icons

export const CHANNEL_LABELS: Record<ChannelKey, string> = {
  voice: "Phone",
  web_chat: "Website chat",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
};

const FEATURE_LABELS: Record<string, string> = {
  google_calendar: "Google Calendar",
  recording_retention: "12-month recordings",
  extra_language: "Extra language",
};

const CHAT_CHANNELS: ChannelKey[] = ["web_chat", "whatsapp", "messenger"];

const ADDON_ICONS: Record<string, LucideIcon> = {
  web_chat: MessageSquare,
  whatsapp: MessageCircle,
  messenger: MessageCircleMore,
  minutes: Timer,
  sms: Smartphone,
  number: PhoneCall,
  google_calendar: CalendarSync,
  extra_language: Languages,
  recording_retention: Archive,
  setup: Handshake,
};

export function addonIcon(key: string): LucideIcon {
  return ADDON_ICONS[key] ?? Puzzle;
}

// ---------------------------------------------------------------- plan & usage

const NEXT_PLAN: Record<string, string> = { trial: "growth", chat: "starter", starter: "growth", growth: "pro", pro: "enterprise" };

/** One allowance this month: `limit` null = unlimited, 0 = none included. */
function Meter({ label, used, limit, unit, moreHref, extra }: { label: string; used: number; limit: number | null; unit: string; moreHref?: string; extra?: string }) {
  const capped = typeof limit === "number" && limit > 0;
  const pct = capped ? Math.min(100, (used / limit) * 100) : 0;
  const over = capped && used > limit;
  const near = capped && !over && pct >= 80;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          <span className="font-semibold text-foreground">{formatNumber(used)}</span>
          {capped ? ` / ${formatNumber(limit, 0)} ${unit}` : limit === null ? ` ${unit} · Unlimited` : ` ${unit} · none included`}
        </span>
      </div>
      {capped && (
        <div
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuenow={Math.min(used, limit)}
          aria-valuetext={`${formatNumber(used)} of ${formatNumber(limit, 0)} ${unit}`}
          className="mt-2 h-2 overflow-hidden rounded-full bg-secondary"
        >
          <div className={cn("h-full rounded-full transition-[width]", over ? "bg-destructive" : near ? "bg-amber-500" : "bg-primary")} style={{ width: `${pct}%` }} />
        </div>
      )}
      {(over || near) && (
        <p className={cn("mt-1.5 flex flex-wrap items-center gap-1.5 text-xs font-medium", over ? "text-destructive" : "text-amber-700 dark:text-amber-300")}>
          <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
          {over ? "Over limit" : "Almost used up"}
          {extra && <span className="font-normal">· {extra}</span>}
          {moreHref && (
            <Link href={moreHref} className="text-primary underline-offset-2 hover:underline">
              Add more
            </Link>
          )}
        </p>
      )}
    </div>
  );
}

export function PlanSection() {
  const { usage, entitlements } = useWorkspace();
  const plan = usage.plan;
  const limits = usage.limits;
  const periodStart = new Date(usage.period_start);
  const since = Number.isNaN(periodStart.getTime())
    ? ""
    : new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", timeZone: "UTC" }).format(periodStart);
  const nextPlan = NEXT_PLAN[plan.key];
  const contactHref = nextPlan ? `/contact?plan=${nextPlan}` : "/contact";
  const voice = entitlements.channels.includes("voice");
  const chat = entitlements.channels.some((channel) => CHAT_CHANNELS.includes(channel));
  const overage = usage.overage_minutes > 0 && plan.overage_per_minute > 0 ? `${formatNumber(usage.overage_minutes)} min · ${usd(usage.overage_minutes * plan.overage_per_minute)}` : undefined;
  const chips = [...(plan.channels ?? []).map((channel) => CHANNEL_LABELS[channel] ?? channel), ...(plan.includes ?? []).map((key) => FEATURE_LABELS[key] ?? key)];

  return (
    <SectionCard
      id="plan"
      icon={CreditCard}
      title="Your plan"
      description={since ? `This month, since ${since}.` : undefined}
      badge={
        <Button asChild size="sm" variant="outline">
          <Link href={contactHref} target="_blank" rel="noopener">
            {nextPlan ? "Upgrade" : "Talk to us"}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Button>
      }
    >
      <div className="grid gap-6 md:grid-cols-[14rem_minmax(0,1fr)]">
        <div className="min-w-0 rounded-md border border-border bg-surface p-4">
          <p className="text-xl font-bold">{plan.name}</p>
          <p className="mt-0.5 text-sm tabular-nums text-muted-foreground">{plan.price_month ? `${usd(plan.price_month)} / mo` : "Free"}</p>
          {chips.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Included">
              {chips.map((chip) => (
                <li key={chip} className="rounded-full bg-accent px-2 py-0.5 text-[11.5px] font-semibold text-accent-foreground">
                  {chip}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="grid min-w-0 content-start gap-5">
          {voice && <Meter label="Call minutes" used={usage.minutes} limit={limits.minutes} unit="min" moreHref="/addons#minutes" extra={overage} />}
          {chat && <Meter label="Chats" used={usage.chats} limit={limits.chats} unit="chats" />}
          <Meter label="Texts" used={usage.sms ?? 0} limit={limits.sms} unit="texts" moreHref="/addons#sms" />
        </div>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- add-on shop (shared with the Channels page)

export function useAddonShop() {
  const [shop, setShop] = useState<AddonShop | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setShop(await addonsApi.shop());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load add-ons."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return { shop, setShop, error, reload: load };
}

export type AddonActions = ReturnType<typeof useAddonActions>;

/** Request / cancel an add-on; the shop comes back updated and the workspace is refreshed. */
export function useAddonActions(onShop: (shop: AddonShop) => void) {
  const { refresh } = useWorkspace();
  const toast = useAppToast();
  const [busy, setBusy] = useState<string | null>(null);

  const request = useCallback(
    async (item: AddonItem, quantity = 1) => {
      setBusy(item.key);
      try {
        onShop(await addonsApi.request(item.key, quantity));
        await refresh();
        toast.success(`${item.name} requested.`);
      } catch (err) {
        toast.error(formatApiError(err, "Could not send the request."));
      } finally {
        setBusy(null);
      }
    },
    [onShop, refresh, toast],
  );

  const cancel = useCallback(
    async (item: AddonItem, pending: AddonRequest) => {
      setBusy(item.key);
      try {
        onShop(await addonsApi.cancelRequest(pending.id));
        await refresh();
        toast.success("Request cancelled.");
      } catch (err) {
        toast.error(formatApiError(err, "Could not cancel the request."));
      } finally {
        setBusy(null);
      }
    },
    [onShop, refresh, toast],
  );

  return { busy, request, cancel };
}

/** The open request for an add-on, if any. */
export function pendingRequest(shop: AddonShop, key: string): AddonRequest | undefined {
  return shop.requests.find((row) => row.addon === key && row.status === "pending");
}

/** The newest request for an add-on (requests come newest first). */
export function latestRequest(shop: AddonShop, key: string): AddonRequest | undefined {
  return shop.requests.find((row) => row.addon === key);
}

const MAX_STEP = 10;

function Stepper({ value, onChange, label }: { value: number; onChange: (value: number) => void; label: string }) {
  const step = "inline-flex h-full w-8 items-center justify-center text-muted-foreground transition hover:text-foreground disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <div role="group" aria-label={label} className="inline-flex h-8 items-center rounded-md border border-input bg-card">
      <button type="button" className={cn(step, "rounded-l-md")} aria-label="Fewer" disabled={value <= 1} onClick={() => onChange(Math.max(1, value - 1))}>
        <Minus className="h-3.5 w-3.5" aria-hidden />
      </button>
      <span className="w-7 text-center text-sm font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button type="button" className={cn(step, "rounded-r-md")} aria-label="More" disabled={value >= MAX_STEP} onClick={() => onChange(Math.min(MAX_STEP, value + 1))}>
        <Plus className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}

/** "Request" (with a quantity stepper for stackable add-ons), or "Requested" + "Cancel" while one is open. */
export function RequestControls({ item, pending, actions }: { item: AddonItem; pending?: AddonRequest; actions: AddonActions }) {
  const [quantity, setQuantity] = useState(1);
  const busy = actions.busy === item.key;
  if (pending) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="warning" className="gap-1.5">
          <Clock className="h-3.5 w-3.5" aria-hidden />
          Requested{item.stackable && pending.quantity > 1 ? ` ×${pending.quantity}` : ""}
        </Badge>
        <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => void actions.cancel(item, pending)}>
          {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
          Cancel
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {item.stackable && <Stepper value={quantity} onChange={setQuantity} label={`How many: ${item.name}`} />}
      <Button type="button" size="sm" disabled={busy} onClick={() => void actions.request(item, item.stackable ? quantity : 1)}>
        {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
        Request
      </Button>
      {item.stackable && quantity > 1 && (
        <span className="text-xs tabular-nums text-muted-foreground">
          {usd(item.price * quantity)}
          {item.period === "once" ? " once" : " / mo"}
        </span>
      )}
    </div>
  );
}

/** Scrolls to (and reports) the element named by the URL hash once `ready`; follows later hash changes. */
export function useHashTarget(ready: boolean): string | null {
  const [target, setTarget] = useState<string | null>(null);
  useEffect(() => {
    if (!ready) return;
    const go = () => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      const element = id ? document.getElementById(id) : null;
      if (!element) return;
      element.scrollIntoView({ behavior: "smooth", block: "start" });
      setTarget(id);
    };
    const frame = window.requestAnimationFrame(go);
    window.addEventListener("hashchange", go);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", go);
    };
  }, [ready]);
  return target;
}
