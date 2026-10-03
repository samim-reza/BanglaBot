"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CircleCheck,
  CircleDashed,
  CirclePlus,
  CircleX,
  Clock3,
  Globe,
  ListChecks,
  PhoneCall,
  PhoneMissed,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { ApiError } from "@/components/api-error";
import { callerName, channelIcon, conversationLength } from "@/components/call-log-list";
import { PageHeader } from "@/components/page-header";
import { UsageMeter } from "@/components/portal/kit";
import { OrderStatusBadge, OutcomeBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { channelLabel, formatInZone, money, statusLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { callsApi, catalogApi, formatApiError, ordersApi, type CallLog, type Order, type OrderStats, type OrderStatus } from "@/services/api";

const STATUS_TILES: { status: OrderStatus; icon: LucideIcon; accent: string; voice?: boolean }[] = [
  { status: "pending", icon: Clock3, accent: "text-[#92400e] dark:text-amber-300" },
  { status: "calling", icon: PhoneCall, accent: "text-[#1d4ed8] dark:text-blue-300", voice: true },
  { status: "confirmed", icon: CircleCheck, accent: "text-[#065f46] dark:text-emerald-300" },
  { status: "cancelled", icon: CircleX, accent: "text-destructive" },
  { status: "no_answer", icon: PhoneMissed, accent: "text-[#5b21b6] dark:text-violet-300", voice: true },
  { status: "needs_review", icon: TriangleAlert, accent: "text-[#9a3412] dark:text-orange-300" },
];

const CHAT_CHANNELS = ["web_chat", "whatsapp", "messenger"] as const;

const fmt = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 1 });

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function ViewAll({ href }: { href: string }) {
  return (
    <Button asChild variant="ghost" size="sm">
      <Link href={href}>
        View all
        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
      </Link>
    </Button>
  );
}

function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-md bg-secondary" />
      ))}
    </div>
  );
}

type Step = { key: string; done: boolean; title: string; href: string; cta: string };

function Checklist({ steps }: { steps: Step[] }) {
  const done = steps.filter((step) => step.done).length;
  return (
    <Card className="border-tint-strong">
      <CardHeader className="gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground" aria-hidden="true">
            <ListChecks className="h-4 w-4" />
          </span>
          <div className="space-y-0.5">
            <CardTitle>Finish setup</CardTitle>
            <CardDescription>
              {done} of {steps.length} done
            </CardDescription>
          </div>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-secondary sm:w-40"
          role="progressbar"
          aria-label="Setup progress"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={done}
        >
          <div className="h-full rounded-full bg-primary" style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
      </CardHeader>
      <CardContent>
        <ol className="grid gap-2 md:grid-cols-2">
          {steps.map((step) => (
            <li key={step.key} className={cn("flex items-center gap-3 rounded-md border border-border p-3", step.done ? "bg-surface" : "bg-card")}>
              {step.done ? (
                <CircleCheck className="h-5 w-5 shrink-0 text-primary" aria-label="Done" />
              ) : (
                <CircleDashed className="h-5 w-5 shrink-0 text-muted-foreground" aria-label="To do" />
              )}
              <p className={cn("min-w-0 flex-1 text-sm font-medium", step.done && "text-muted-foreground line-through decoration-muted-foreground/50")}>{step.title}</p>
              {!step.done && (
                <Button asChild size="sm" variant="outline" className="shrink-0">
                  <Link href={step.href}>{step.cta}</Link>
                </Button>
              )}
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function RecordRow({ order, scheduled }: { order: Order; scheduled: boolean }) {
  const { vertical, merchant } = useWorkspace();
  const detail = order.summary || order.catalog_item_name || order.customer_phone;
  return (
    <li>
      <Link
        href={`/orders/${order.id}`}
        className="flex items-center gap-3 rounded-md px-2 py-2.5 transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{order.customer_name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {scheduled && order.scheduled_at ? `${formatInZone(order.scheduled_at, merchant.timezone)} · ` : ""}
            {detail}
          </p>
        </div>
        <OrderStatusBadge status={order.status} spec={vertical} className="shrink-0" />
      </Link>
    </li>
  );
}

function CallRow({ log }: { log: CallLog }) {
  const { merchant } = useWorkspace();
  const Icon = channelIcon(log.direction);
  return (
    <li>
      <Link
        href={log.order_id ? `/orders/${log.order_id}` : "/calls"}
        className="flex items-center gap-3 rounded-md px-2 py-2.5 transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground" aria-hidden="true">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{callerName(log)}</p>
          <p className="truncate text-xs text-muted-foreground">
            {channelLabel(log.direction)} · {conversationLength(log)} · {formatInZone(log.created_at, merchant.timezone)}
          </p>
        </div>
        <OutcomeBadge outcome={log.outcome} callStatus={log.call_status} className="shrink-0" />
      </Link>
    </li>
  );
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
  const limits = usage.limits;

  const [stats, setStats] = useState<OrderStats | null>(null);
  const [records, setRecords] = useState<Order[] | null>(null);
  const [calls, setCalls] = useState<CallLog[] | null>(null);
  const [catalogCount, setCatalogCount] = useState<number | null>(hasCatalog ? null : 0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [statsResult, recordsResult, callsResult] = await Promise.allSettled([
      ordersApi.stats(),
      vertical.scheduled ? ordersApi.list({ upcoming: true, sort: "scheduled", page_size: 5 }) : ordersApi.list({ page_size: 5 }),
      callsApi.list({ page_size: 5 }),
    ]);
    const failures: unknown[] = [];
    if (statsResult.status === "fulfilled") setStats(statsResult.value);
    else failures.push(statsResult.reason);
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
    setError(failures.length ? formatApiError(failures[0], "Could not load part of the dashboard.") : null);
  }, [vertical.scheduled]);

  useEffect(() => {
    void load();
  }, [load]);

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

  // Keep the tiles fresh while calls are in flight.
  useEffect(() => {
    if (!stats?.calling) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [stats?.calling, load]);

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
  steps.push({
    key: "knowledge",
    done: Boolean(merchant.knowledge?.trim()),
    title: "Teach your agent your business",
    href: "/settings?tab=agent#knowledge",
    cta: "Add info",
  });
  if (hasWebChat) {
    steps.push({ key: "widget", done: merchant.widget_enabled, title: "Turn on website chat", href: "/channels#web-chat", cta: "Set up" });
  }
  if (hasVoice && vertical.directions.includes("inbound")) {
    steps.push({ key: "number", done: Boolean(merchant.inbound_number), title: "Connect a phone number", href: "/channels#phone", cta: "Set up" });
  }
  const checklistReady = !hasCatalog || catalogCount !== null;
  const showChecklist = checklistReady && steps.some((step) => !step.done);

  const tiles = STATUS_TILES.filter((tile) => hasVoice || !tile.voice);

  const quickActions: { href: string; label: string; icon: LucideIcon }[] = [
    hasCatalog
      ? { href: "/catalog", label: `Add ${catalogSingular.toLowerCase()}`, icon: CirclePlus }
      : { href: "/orders/new", label: `New ${singular.toLowerCase()}`, icon: CirclePlus },
    ...(hasWebChat ? [{ href: "/channels#web-chat", label: "Website chat", icon: Globe }] : []),
  ];

  const minutesLimit = limits.minutes;
  const minutesNote =
    minutesLimit === null || minutesLimit <= 0
      ? null
      : usage.overage_minutes > 0
        ? `${fmt(usage.overage_minutes)} min over${usage.plan.overage_per_minute ? ` · ${money(usage.plan.overage_per_minute, "USD")}/min` : ""}`
        : `${fmt(usage.minutes_left ?? Math.max(0, minutesLimit - usage.minutes))} min left`;

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
      <ApiError message={error} />

      {showChecklist && <Checklist steps={steps} />}

      <section aria-label={`${plural} by status`} className={cn("grid grid-cols-2 gap-3 sm:grid-cols-4", hasVoice ? "xl:grid-cols-7" : "xl:grid-cols-5")}>
        {tiles.map(({ status, icon: Icon, accent }) => (
          <Link
            key={status}
            href={`/orders?status=${status}`}
            className="group rounded-lg border border-border bg-card p-4 transition hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex items-center justify-between gap-2">
              <span className="truncate text-[13px] font-medium text-muted-foreground">{statusLabel(vertical, status)}</span>
              <Icon className={cn("h-4 w-4 shrink-0", accent)} aria-hidden="true" />
            </span>
            <span className="mt-2 block text-[26px] font-bold leading-tight tabular-nums">{stats ? stats[status] : "—"}</span>
          </Link>
        ))}
        <Link
          href="/orders"
          className={cn(
            "rounded-lg border border-border bg-surface p-4 transition hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring xl:col-span-1",
            hasVoice ? "col-span-2 sm:col-span-2" : "col-span-2 sm:col-span-4",
          )}
        >
          <span className="text-[13px] font-medium text-muted-foreground">All {plural.toLowerCase()}</span>
          <span className="mt-2 block text-[26px] font-bold leading-tight tabular-nums">{stats ? stats.total : "—"}</span>
        </Link>
      </section>

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
          <Card>
            <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
              <div className="space-y-1">
                <CardTitle>This month</CardTitle>
                <CardDescription>Since {formatDate(usage.period_start)}</CardDescription>
              </div>
              <span className="rounded-full bg-accent px-2.5 py-0.5 text-[12px] font-semibold text-accent-foreground">{usage.plan.name}</span>
            </CardHeader>
            <CardContent className="space-y-4">
              {hasVoice && (
                <div>
                  <UsageMeter label="Call minutes" used={usage.minutes} included={limits.minutes} unit="min" />
                  {minutesNote && <p className="mt-1.5 text-xs text-muted-foreground">{minutesNote}</p>}
                </div>
              )}
              {hasChat && <UsageMeter label="Chats" used={usage.chats} included={limits.chats} unit="chats" />}
              <UsageMeter label="Texts" used={usage.sms ?? 0} included={limits.sms} unit="texts" />
              {hasVoice && (
                <dl className="flex items-baseline justify-between gap-3 border-t border-border pt-4 text-sm">
                  <dt className="text-muted-foreground">Calls</dt>
                  <dd className="text-lg font-semibold tabular-nums">{usage.calls.toLocaleString("en-US")}</dd>
                </dl>
              )}
            </CardContent>
          </Card>

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
