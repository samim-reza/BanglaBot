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
  FlaskConical,
  Globe,
  ListChecks,
  MessageSquare,
  MonitorSmartphone,
  Phone,
  PhoneCall,
  PhoneIncoming,
  PhoneMissed,
  PhoneOutgoing,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { ApiError } from "@/components/api-error";
import { conversationLength } from "@/components/call-log-list";
import { UsageBar } from "@/components/merchant-shell";
import { PageHeader } from "@/components/page-header";
import { OrderStatusBadge, OutcomeBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { channelLabel, formatInZone, money, statusLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { callsApi, catalogApi, formatApiError, ordersApi, type CallLog, type Order, type OrderStats, type OrderStatus } from "@/services/api";

const STATUS_TILES: { status: OrderStatus; icon: LucideIcon; accent: string }[] = [
  { status: "pending", icon: Clock3, accent: "text-[#92400e] dark:text-amber-300" },
  { status: "calling", icon: PhoneCall, accent: "text-[#1d4ed8] dark:text-blue-300" },
  { status: "confirmed", icon: CircleCheck, accent: "text-[#065f46] dark:text-emerald-300" },
  { status: "cancelled", icon: CircleX, accent: "text-destructive" },
  { status: "no_answer", icon: PhoneMissed, accent: "text-[#5b21b6] dark:text-violet-300" },
  { status: "needs_review", icon: TriangleAlert, accent: "text-[#9a3412] dark:text-orange-300" },
];

const CHANNEL_ICONS: Record<string, LucideIcon> = {
  inbound: PhoneIncoming,
  outbound: PhoneOutgoing,
  widget: Globe,
  web: MonitorSmartphone,
  chat: MessageSquare,
};

const fmt = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 1 });

function Section({ title, description, action, children }: { title: string; description?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
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

type Step = { key: string; done: boolean; title: string; body: string; href: string; cta: string };

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
            <CardTitle>Finish setting up your agent</CardTitle>
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
            <li
              key={step.key}
              className={cn("flex items-start gap-3 rounded-md border border-border p-3", step.done ? "bg-surface" : "bg-card")}
            >
              {step.done ? (
                <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-label="Done" />
              ) : (
                <CircleDashed className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-label="To do" />
              )}
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm font-medium", step.done && "text-muted-foreground line-through decoration-muted-foreground/50")}>{step.title}</p>
                {!step.done && <p className="mt-0.5 text-xs text-muted-foreground">{step.body}</p>}
              </div>
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
  const Icon = CHANNEL_ICONS[log.direction] ?? Phone;
  const name = log.customer_name || log.caller_number || (log.direction === "widget" ? "Website visitor" : "Test");
  const body = (
    <>
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground" aria-hidden="true">
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {channelLabel(log.direction)} · {conversationLength(log)} · {formatInZone(log.created_at, merchant.timezone)}
        </p>
      </div>
      <OutcomeBadge outcome={log.outcome} callStatus={log.call_status} className="shrink-0" />
    </>
  );
  const className = "flex items-center gap-3 rounded-md px-2 py-2.5 transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <li>
      {log.order_id ? (
        <Link href={`/orders/${log.order_id}`} className={className}>
          {body}
        </Link>
      ) : (
        <Link href="/calls" className={className}>
          {body}
        </Link>
      )}
    </li>
  );
}

export default function DashboardPage() {
  const { merchant, vertical, usage } = useWorkspace();
  const singular = t(vertical.record_label, "Record");
  const plural = t(vertical.record_label_plural, "Records");
  const catalogSingular = t(vertical.catalog_label, "item");
  const catalogPlural = t(vertical.catalog_label_plural, "catalog");
  const hasCatalog = Boolean(vertical.catalog_kind);

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
      body: "Your agent only offers and books what is on this list.",
      href: "/catalog",
      cta: `Add ${catalogSingular.toLowerCase()}`,
    });
  }
  steps.push({
    key: "knowledge",
    done: Boolean(merchant.knowledge?.trim()),
    title: "Teach your agent about your business",
    body: "Hours, prices, policies and common questions it should answer.",
    href: "/settings",
    cta: "Add knowledge",
  });
  steps.push({
    key: "widget",
    done: merchant.widget_enabled,
    title: "Turn on website chat",
    body: "Let visitors chat with the same agent on your website.",
    href: "/addons",
    cta: "Embed chat",
  });
  if (vertical.directions.includes("inbound")) {
    steps.push({
      key: "number",
      done: Boolean(merchant.inbound_number),
      title: "Connect a phone number",
      body: "Callers reach your agent once a number is connected to your account.",
      href: "/settings",
      cta: "Set up",
    });
  }
  const checklistReady = !hasCatalog || catalogCount !== null;
  const showChecklist = checklistReady && steps.some((step) => !step.done);

  const included = usage.plan.included_minutes;
  const includedChats = usage.plan.included_chats;

  const quickActions: { href: string; label: string; hint: string; icon: LucideIcon }[] = [
    { href: "/test", label: "Test your agent", hint: "Call or chat with it from your browser.", icon: FlaskConical },
    ...(hasCatalog
      ? [{ href: "/catalog", label: `Add ${catalogSingular.toLowerCase()}`, hint: `Keep your ${catalogPlural.toLowerCase()} up to date.`, icon: CirclePlus }]
      : [{ href: "/orders/new", label: `New ${singular.toLowerCase()}`, hint: `Add a ${singular.toLowerCase()} by hand.`, icon: CirclePlus }]),
    { href: "/addons", label: "Embed website chat", hint: "Copy one snippet into your site.", icon: Globe },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={merchant.business_name}
        subtitle={`${t(vertical.label)} · here is what your agent has handled.`}
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

      <section aria-label={`${plural} by status`} className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {STATUS_TILES.map(({ status, icon: Icon, accent }) => (
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
          className="col-span-2 rounded-lg border border-border bg-surface p-4 transition hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:col-span-2 xl:col-span-1"
        >
          <span className="text-[13px] font-medium text-muted-foreground">All {plural.toLowerCase()}</span>
          <span className="mt-2 block text-[26px] font-bold leading-tight tabular-nums">{stats ? stats.total : "—"}</span>
        </Link>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Section
            title={vertical.scheduled ? "Upcoming" : `Recent ${plural.toLowerCase()}`}
            description={vertical.scheduled ? `The next ${plural.toLowerCase()} on your calendar (${merchant.timezone}).` : undefined}
            action={
              <Button asChild variant="ghost" size="sm">
                <Link href={vertical.scheduled ? "/orders?upcoming=1" : "/orders"}>
                  View all
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </Button>
            }
          >
            {records === null ? (
              <SkeletonRows />
            ) : records.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                {vertical.scheduled ? `Nothing coming up yet. New ${plural.toLowerCase()} your agent books appear here.` : `No ${plural.toLowerCase()} yet.`}
              </p>
            ) : (
              <ul className="-mx-2 divide-y divide-border">
                {records.map((order) => (
                  <RecordRow key={order.id} order={order} scheduled={vertical.scheduled} />
                ))}
              </ul>
            )}
          </Section>

          <Section
            title="Recent calls & chats"
            action={
              <Button asChild variant="ghost" size="sm">
                <Link href="/calls">
                  View all
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </Button>
            }
          >
            {calls === null ? (
              <SkeletonRows />
            ) : calls.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                No conversations yet.{" "}
                <Link href="/test" className="font-medium text-primary-dark hover:underline">
                  Test your agent
                </Link>{" "}
                to see the first one here.
              </p>
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
              <div>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm text-muted-foreground">Call minutes</span>
                  <span className="text-sm tabular-nums">
                    <span className="text-lg font-semibold">{fmt(usage.minutes)}</span>
                    {included ? <span className="text-muted-foreground"> / {fmt(included)}</span> : null}
                  </span>
                </div>
                <UsageBar usage={usage} className="mt-2" />
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {!included
                    ? "Custom volume plan."
                    : usage.overage_minutes > 0
                      ? `${fmt(usage.overage_minutes)} min over your plan${usage.plan.overage_per_minute ? `, billed at ${money(usage.plan.overage_per_minute, "USD")}/min` : ""}.`
                      : `${fmt(usage.minutes_left ?? Math.max(0, included - usage.minutes))} min left`}
                </p>
              </div>
              <dl className="grid grid-cols-3 gap-3 border-t border-border pt-4">
                <div>
                  <dt className="text-xs text-muted-foreground">Calls</dt>
                  <dd className="text-lg font-semibold tabular-nums">{usage.calls.toLocaleString("en-US")}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Chats</dt>
                  <dd className="text-lg font-semibold tabular-nums">
                    {usage.chats.toLocaleString("en-US")}
                    {includedChats ? <span className="text-sm font-normal text-muted-foreground"> / {includedChats.toLocaleString("en-US")}</span> : null}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Texts</dt>
                  <dd className="text-lg font-semibold tabular-nums">
                    {(usage.sms ?? 0).toLocaleString("en-US")}
                    {usage.plan.included_sms ? <span className="text-sm font-normal text-muted-foreground"> / {usage.plan.included_sms.toLocaleString("en-US")}</span> : null}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Section title="Quick actions">
            <ul className="-mx-2 space-y-1">
              {quickActions.map((action) => (
                <li key={action.href + action.label}>
                  <Link
                    href={action.href}
                    className="flex items-center gap-3 rounded-md px-2 py-2.5 transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground" aria-hidden="true">
                      <action.icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">{action.label}</span>
                      <span className="block truncate text-xs text-muted-foreground">{action.hint}</span>
                    </span>
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
