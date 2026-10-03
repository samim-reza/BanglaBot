"use client";

/** Chat channels on the Channels page: WhatsApp, Messenger, and the locked card for channels not on the plan. */

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ExternalLink, Info, LoaderCircle, Lock, MessageCircle, MessageCircleMore, Unplug, type LucideIcon } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { HoverInfo } from "@/components/ui/hover-info";
import { Input } from "@/components/ui/input";
import { useCopy, CopyButton, SectionCard, StatusPill, InlineError, SetupNote } from "@/components/portal/kit";
import { RequestControls, pendingRequest, type AddonActions } from "@/components/portal/plan-section";
import { useWorkspace } from "@/lib/workspace";
import { channelsApi, formatApiError, type AddonShop, type ChannelsView } from "@/services/api";

/** GET /api/channels — platform readiness and the latest channel setup; null until loaded (or if it fails). */
export function useChannelsView() {
  const [view, setView] = useState<ChannelsView | null>(null);
  useEffect(() => {
    let alive = true;
    channelsApi
      .get()
      .then((next) => {
        if (alive) setView(next);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return { view, setView };
}

// ---------------------------------------------------------------- locked / upsell

export function LockedCard({ id, icon, title, line, price, action }: { id: string; icon: LucideIcon; title: string; line?: string; price?: string; action: React.ReactNode }) {
  return (
    <SectionCard
      id={id}
      icon={icon}
      title={title}
      description={line}
      className="border-dashed"
      badge={
        <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-[12.5px] font-semibold tabular-nums text-muted-foreground">
          <Lock className="h-3 w-3" aria-hidden />
          {price ?? "Locked"}
        </span>
      }
    >
      {action}
    </SectionCard>
  );
}

/** A channel the plan doesn't include: its add-on, with "Request" (or a link to the shop until it loads). */
export function LockedAddon({ id, addonKey, icon, title, shop, actions }: { id: string; addonKey: string; icon: LucideIcon; title: string; shop: AddonShop | null; actions: AddonActions }) {
  const item = shop?.catalog.find((entry) => entry.key === addonKey);
  const requestable = Boolean(item && shop?.available.includes(addonKey));
  return (
    <LockedCard
      id={id}
      icon={icon}
      title={title}
      line={item?.summary ?? "Available as an add-on."}
      price={item?.price_label}
      action={
        item && shop && requestable ? (
          <RequestControls item={item} pending={pendingRequest(shop, addonKey)} actions={actions} />
        ) : (
          <Button asChild variant="outline" size="sm">
            <Link href={`/addons#${addonKey}`}>
              See add-on
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </Button>
        )
      }
    />
  );
}

// ---------------------------------------------------------------- WhatsApp

export function WhatsAppSection({ view }: { view: ChannelsView | null }) {
  const { merchant } = useWorkspace();
  const { copied, copy } = useCopy();
  const number = (view?.whatsapp.number ?? merchant.channels?.whatsapp?.number ?? "").replace(/^whatsapp:/i, "").trim();
  const digits = number.replace(/\D/g, "");
  const platformReady = view ? view.platform.whatsapp_ready : true;
  return (
    <SectionCard
      id="whatsapp"
      icon={MessageCircle}
      title="WhatsApp"
      badge={<StatusPill ok={Boolean(number) && platformReady}>{number ? (platformReady ? "Live" : "Paused") : "Setting up"}</StatusPill>}
    >
      <div className="space-y-3 text-sm">
        {number ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-lg font-semibold tabular-nums">{number}</span>
              <CopyButton id="whatsapp-number" text={number} copied={copied} onCopy={copy} />
              {digits && (
                <Button asChild variant="outline" size="sm">
                  <a href={`https://wa.me/${digits}`} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                    Open chat
                  </a>
                </Button>
              )}
            </div>
            <p className="text-muted-foreground">Share this number with your customers.</p>
          </>
        ) : (
          <p className="text-muted-foreground">Number being set up — we&apos;ll add it for you.</p>
        )}
        {!platformReady && <SetupNote>WhatsApp isn&apos;t set up on this server yet.</SetupNote>}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- Messenger

const PAGE_ID = /^\d{3,40}$/;

function MessengerHelp() {
  const steps = ["Open your app on developers.facebook.com.", "Messenger → Settings → add your Page.", "Generate a token; copy it and the Page ID."];
  return (
    <HoverInfo
      width={280}
      trigger={
        <span tabIndex={0} className="inline-flex cursor-help items-center gap-1 rounded text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Info className="h-3.5 w-3.5" aria-hidden />
          How to get these
          <span className="sr-only">: {steps.map((step, index) => `${index + 1}. ${step}`).join(" ")}</span>
        </span>
      }
    >
      <ol className="list-decimal space-y-1 pl-4 text-xs leading-relaxed text-foreground" aria-hidden>
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </HoverInfo>
  );
}

export function MessengerSection({ view, onView }: { view: ChannelsView | null; onView: (next: ChannelsView) => void }) {
  const { merchant, refresh } = useWorkspace();
  const toast = useAppToast();
  const page = view?.messenger ?? merchant.channels?.messenger ?? { page_id: "", page_name: "", connected: false };
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async (event: FormEvent) => {
    event.preventDefault();
    const id = pageId.trim();
    const secret = token.trim();
    if (!PAGE_ID.test(id)) {
      setError("The Page ID is a number, like 1234567890.");
      return;
    }
    if (secret.length < 20) {
      setError("Paste the full Page access token.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onView(await channelsApi.connectMessenger(id, secret));
      setPageId("");
      setToken("");
      await refresh();
      toast.success("Messenger connected.");
    } catch (err) {
      setError(formatApiError(err, "Could not connect the Page."));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect this Page?\n\nThe bot stops answering its messages.")) return;
    setBusy(true);
    try {
      onView(await channelsApi.disconnectMessenger());
      await refresh();
      toast.success("Messenger disconnected.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not disconnect the Page."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard
      id="messenger"
      icon={MessageCircleMore}
      title="Messenger"
      badge={<StatusPill ok={page.connected}>{page.connected ? "Connected" : "Not connected"}</StatusPill>}
    >
      <div className="space-y-3 text-sm">
        {page.connected ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="min-w-0">
              <span className="font-semibold">{page.page_name || "Facebook Page"}</span>
              {page.page_id && <span className="ml-2 font-mono text-xs text-muted-foreground">ID {page.page_id}</span>}
            </p>
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void disconnect()}>
              {busy ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Unplug className="h-3.5 w-3.5" aria-hidden />}
              Disconnect
            </Button>
          </div>
        ) : (
          <form onSubmit={connect} noValidate className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">Connect your Facebook Page</p>
              <MessengerHelp />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="messenger-page-id" className="text-[13.5px] font-semibold text-muted-foreground">
                  Page ID
                </label>
                <Input
                  id="messenger-page-id"
                  value={pageId}
                  inputMode="numeric"
                  autoComplete="off"
                  spellCheck={false}
                  maxLength={40}
                  placeholder="1234567890"
                  className="font-mono"
                  onChange={(e) => setPageId(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="messenger-page-token" className="text-[13.5px] font-semibold text-muted-foreground">
                  Page access token
                </label>
                <Input
                  id="messenger-page-token"
                  type="password"
                  value={token}
                  autoComplete="off"
                  spellCheck={false}
                  maxLength={600}
                  className="font-mono"
                  onChange={(e) => setToken(e.target.value)}
                />
              </div>
            </div>
            <InlineError message={error} />
            <Button type="submit" size="sm" disabled={busy || !pageId.trim() || !token.trim()}>
              {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Connect
            </Button>
          </form>
        )}
        {view && !view.platform.messenger_ready && <SetupNote>Messenger isn&apos;t set up on this server yet.</SetupNote>}
      </div>
    </SectionCard>
  );
}
