"use client";

/**
 * The owner's dashboard: proof of what the agent did ("Your agent this week": answered,
 * booked, after hours …), outbound call results only for accounts that place calls,
 * what's coming up, recent conversations and this month's usage.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CirclePlus, Globe, type LucideIcon } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { AgentSummary } from "@/components/portal/dashboard/agent-summary";
import { Checklist, type Step } from "@/components/portal/dashboard/checklist";
import { MonthCard } from "@/components/portal/dashboard/month-card";
import { OutboundCalls } from "@/components/portal/dashboard/outbound-summary";
import { Section, SkeletonRows, SkeletonTiles, ViewAll } from "@/components/portal/dashboard/parts";
import { CallRow, RecordRow } from "@/components/portal/dashboard/rows";
import { usePhoneRequest } from "@/components/portal/phone-request";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { callsApi, catalogApi, dashboardApi, formatApiError, ordersApi, type CallLog, type DashboardRange, type DashboardSummary, type Order } from "@/services/api";

const CHAT_CHANNELS = ["web_chat", "whatsapp", "messenger"] as const;
const RANGE_KEY = "callisa_dashboard_range";
const RANGE_TITLES: Record<DashboardRange, string> = { today: "today", "7d": "this week", "30d": "last 30 days" };

function savedRange(): DashboardRange {
  try {
    const value = window.localStorage.getItem(RANGE_KEY);
    return value === "today" || value === "30d" ? value : "7d";
  } catch {
    return "7d";
  }
}

export default function DashboardPage() {
  const { merchant, vertical, usage, entitlements } = useWorkspace();
  const singular = t(vertical.record_label, "Record");
  const plural = t(vertical.record_label_plural, "Records");
  const catalogSingular = t(vertical.catalog_label, "item");
  const catalogPlural = t(vertical.catalog_label_plural, "catalog");
  const hasCatalog = Boolean(vertical.catalog_kind);
  const channels = entitlements.channels;
  // A chat-only plan has no phone agent: no minutes, calls or call statuses.
  const hasVoice = channels.includes("voice");
  const hasChat = CHAT_CHANNELS.some((channel) => channels.includes(channel)) || usage.chats > 0;
  const hasWebChat = channels.includes("web_chat");
  const hasInbound = vertical.directions.includes("inbound");
  const inboundFirst = vertical.key !== "ecommerce" && hasInbound;

  // null until the remembered period is read (no wasted first load).
  const [range, setRange] = useState<DashboardRange | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [records, setRecords] = useState<Order[] | null>(null);
  const [calls, setCalls] = useState<CallLog[] | null>(null);
  const [catalogCount, setCatalogCount] = useState<number | null>(hasCatalog ? null : 0);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  useEffect(() => setRange(savedRange()), []);

  const chooseRange = (value: DashboardRange) => {
    setRange(value);
    try {
      window.localStorage.setItem(RANGE_KEY, value);
    } catch {
      // A remembered period is a convenience only.
    }
  };

  const loadSummary = useCallback(async (key: DashboardRange) => {
    try {
      setSummary(await dashboardApi.summary(key));
      setSummaryError(null);
    } catch (err) {
      setSummaryError(formatApiError(err, "Could not load your agent's numbers."));
    }
  }, []);

  const loadLists = useCallback(async () => {
    const [recordsResult, callsResult] = await Promise.allSettled([
      vertical.scheduled ? ordersApi.list({ upcoming: true, sort: "scheduled", page_size: 5 }) : ordersApi.list({ page_size: 5 }),
      callsApi.list({ page_size: 5 }),
    ]);
    const failures: unknown[] = [];
    if (recordsResult.status === "fulfilled") setRecords(recordsResult.value.items);
    else {
      failures.push(recordsResult.reason);
      setRecords((current) => current ?? []);
    }
    if (callsResult.status === "fulfilled") setCalls(callsResult.value.items);
    else {
      failures.push(callsResult.reason);
      setCalls((current) => current ?? []);
    }
    setListError(failures.length ? formatApiError(failures[0], "Could not load part of the dashboard.") : null);
  }, [vertical.scheduled]);

  useEffect(() => {
    if (range) void loadSummary(range);
  }, [range, loadSummary]);

  useEffect(() => {
    void loadLists();
  }, [loadLists]);

  useEffect(() => {
    if (!hasCatalog) return;
    let cancelled = false;
    catalogApi
      .list()
      .then((items) => {
        if (!cancelled) setCatalogCount(items.length);
      })
      .catch(() => {
        // The checklist just skips the catalog step if the list can't load.
        if (!cancelled) setCatalogCount(-1);
      });
    return () => {
      cancelled = true;
    };
  }, [hasCatalog]);

  // Keep the numbers fresh while outbound calls are in flight.
  const calling = summary?.outbound?.statuses.calling ?? 0;
  useEffect(() => {
    if (!calling || !range) return;
    const timer = window.setInterval(() => {
      void loadSummary(range);
      void loadLists();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [calling, range, loadSummary, loadLists]);

  const needsNumber = hasVoice && hasInbound && !merchant.inbound_number;
  const phone = usePhoneRequest(needsNumber);
  const steps: Step[] = [];
  if (hasCatalog && catalogCount !== null && catalogCount >= 0) {
    steps.push({
      key: "catalog",
      done: catalogCount > 0,
      title: `Add your ${catalogPlural.toLowerCase()}`,
      href: "/catalog",
      cta: `Add ${catalogSingular.toLowerCase()}`,
    });
  }
  steps.push({ key: "knowledge", done: Boolean(merchant.knowledge?.trim()), title: "Teach your agent your business", href: "/settings?tab=agent#knowledge", cta: "Add info" });
  if (hasWebChat) {
    steps.push({ key: "widget", done: merchant.widget_enabled, title: "Turn on website chat", href: "/channels#web-chat", cta: "Set up" });
  }
  if (hasVoice && hasInbound) {
    steps.push({
      key: "number",
      done: Boolean(merchant.inbound_number),
      title: "Get a phone number",
      note: phone.requested ? "Requested — we'll assign it." : "We assign it for you.",
      action: phone.action,
    });
  }
  const checklistReady = !hasCatalog || catalogCount !== null;
  const showChecklist = checklistReady && steps.some((step) => !step.done);

  const quickActions: { href: string; label: string; icon: LucideIcon }[] = [
    hasCatalog
      ? { href: "/catalog", label: `Add ${catalogSingular.toLowerCase()}`, icon: CirclePlus }
      : { href: "/orders/new", label: `New ${singular.toLowerCase()}`, icon: CirclePlus },
    ...(hasWebChat ? [{ href: "/channels#web-chat", label: "Website chat", icon: Globe }] : []),
  ];

  const agent = hasInbound ? <AgentSummary summary={summary} range={range ?? "7d"} onRange={chooseRange} hasVoice={hasVoice} hasChat={hasChat} /> : null;
  const outbound = summary?.outbound ? (
    <OutboundCalls outbound={summary.outbound} title={RANGE_TITLES[summary.range]} hasVoice={hasVoice} />
  ) : !inboundFirst && !summary ? (
    <SkeletonTiles count={6} />
  ) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={merchant.business_name}
        subtitle={t(vertical.label)}
        actions={
          <Button asChild>
            <Link href="/orders/new">
              <CirclePlus className="h-4 w-4" aria-hidden="true" />
              New {singular.toLowerCase()}
            </Link>
          </Button>
        }
      />
      <ApiError message={summaryError ?? listError} />

      {showChecklist && <Checklist steps={steps} />}

      {inboundFirst ? (
        <>
          {agent}
          {outbound}
        </>
      ) : (
        <>
          {outbound}
          {agent}
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Section
            title={vertical.scheduled ? "Upcoming" : `Recent ${plural.toLowerCase()}`}
            action={<ViewAll href={vertical.scheduled ? "/orders?upcoming=1" : "/orders"} />}
          >
            {records === null ? (
              <SkeletonRows />
            ) : records.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">{vertical.scheduled ? "Nothing coming up." : `No ${plural.toLowerCase()} yet.`}</p>
            ) : (
              <ul className="-mx-2 divide-y divide-border">
                {records.map((order) => (
                  <RecordRow key={order.id} order={order} scheduled={vertical.scheduled} />
                ))}
              </ul>
            )}
          </Section>

          <Section title={hasVoice ? "Recent calls & chats" : "Recent chats"} action={<ViewAll href="/calls" />}>
            {calls === null ? (
              <SkeletonRows />
            ) : calls.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">No conversations yet.</p>
            ) : (
              <ul className="-mx-2 divide-y divide-border">
                {calls.map((log) => (
                  <CallRow key={log.id} log={log} />
                ))}
              </ul>
            )}
          </Section>
        </div>

        <div className="space-y-6">
          <MonthCard hasVoice={hasVoice} hasChat={hasChat} />

          <Section title="Quick actions">
            <ul className="-mx-2 space-y-1">
              {quickActions.map((action) => (
                <li key={action.href + action.label}>
                  <Link
                    href={action.href}
                    className="flex items-center gap-3 rounded-md px-2 py-2 transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground" aria-hidden="true">
                      <action.icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{action.label}</span>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
