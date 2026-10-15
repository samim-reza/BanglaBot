"use client";

/** Add-on shop helpers shared by the Plan & add-ons and Channels pages (labels, icons, requests). */

import { useCallback, useEffect, useState } from "react";
import {
  Archive,
  CalendarSync,
  Clock,
  Handshake,
  Languages,
  LoaderCircle,
  MessageCircle,
  MessageCircleMore,
  MessageSquare,
  Camera,
  Minus,
  PhoneCall,
  Plus,
  Puzzle,
  Smartphone,
  Timer,
  type LucideIcon,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usd } from "@/components/portal/kit";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { addonsApi, formatApiError, type AddonItem, type AddonRequest, type AddonShop, type ChannelKey } from "@/services/api";

// ---------------------------------------------------------------- labels + icons

export const CHANNEL_LABELS: Record<ChannelKey, string> = {
  voice: "Phone",
  web_chat: "Website chat",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
  instagram: "Instagram",
};

const ADDON_ICONS: Record<string, LucideIcon> = {
  web_chat: MessageSquare,
  whatsapp: MessageCircle,
  messenger: MessageCircleMore,
  instagram: Camera,
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
