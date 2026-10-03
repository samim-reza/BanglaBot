"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight, Building2, CalendarCheck, ClipboardList, Inbox, PhoneCall, PhoneIncoming, Plus, RefreshCw } from "lucide-react";

import { KpiTile } from "@/components/admin/stats";
import { useAdminMeta, verticalName } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { t } from "@/lib/vertical";
import { adminApi, formatApiError, type AdminOverview } from "@/services/api";

const fmt = (value: number | undefined) => (value === undefined ? "—" : value.toLocaleString("en-US"));

export default function AdminOverviewPage() {
  const { meta } = useAdminMeta();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [newInquiries, setNewInquiries] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    const [overviewResult, inquiriesResult] = await Promise.allSettled([
      adminApi.overview(),
      adminApi.inquiries({ status: "new", page_size: 1 }),
    ]);
    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value);
      setError(null);
    } else {
      setError(formatApiError(overviewResult.reason, "Could not load the overview."));
    }
    if (inquiriesResult.status === "fulfilled") setNewInquiries(inquiriesResult.value.total);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const o = overview;
  const inactive = o ? Math.max(0, o.merchants - o.active_merchants) : 0;

  // Every business type from meta (zero rows included), then any extra keys the API reports.
  const verticalRows = (() => {
    if (!o) return [] as { key: string; label: string; description: string; count: number }[];
    const keys = meta?.verticals.map((spec) => spec.key as string) ?? [];
    for (const key of Object.keys(o.by_vertical ?? {})) if (!keys.includes(key)) keys.push(key);
    return keys.map((key) => {
      const spec = meta?.verticals.find((item) => item.key === key);
      return {
        key,
        label: verticalName(meta, key),
        description: spec ? t(spec.description) : "",
        count: o.by_vertical?.[key] ?? 0,
      };
    });
  })();
  const maxVertical = Math.max(1, ...verticalRows.map((row) => row.count));

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Platform-wide activity across every account. “Today” runs from midnight on the platform clock (Asia/Dhaka)."
        actions={
          <>
            <Button variant="outline" onClick={() => void load()} disabled={refreshing} aria-label="Refresh overview">
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin motion-reduce:animate-none" : ""}`} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <Button asChild>
              <Link href="/admin/merchants?create=1">
                <Plus className="h-4 w-4" />
                Create account
              </Link>
            </Button>
          </>
        }
      />
      <ApiError message={error} />

      <section aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <KpiTile label="Accounts" icon={Building2} href="/admin/merchants" value={fmt(o?.merchants)} hint={o ? `${fmt(o.orders)} records in total` : undefined} />
        <KpiTile
          label="Active accounts"
          icon={Activity}
          value={fmt(o?.active_merchants)}
          hint={o ? (inactive ? `${fmt(inactive)} inactive` : "All accounts active") : undefined}
        />
        <KpiTile
          label="Calls today"
          icon={PhoneCall}
          href="/admin/calls"
          value={fmt(o?.calls_today)}
          hint={o ? `Every channel · ${fmt(o.confirmed_today)} confirmed, ${fmt(o.cancelled_today)} cancelled` : undefined}
        />
        <KpiTile
          label="Inbound calls today"
          icon={PhoneIncoming}
          href="/admin/calls?direction=inbound"
          value={fmt(o?.inbound_today)}
          hint="Calls answered on account numbers"
        />
        <KpiTile
          label="Bookings today"
          icon={CalendarCheck}
          value={fmt(o?.booked_today)}
          hint={o ? `${fmt(o.orders_today)} new records today` : undefined}
        />
        <KpiTile
          label="Needs review"
          icon={ClipboardList}
          href="/admin/orders?status=needs_review"
          value={fmt(o?.needs_review_orders)}
          emphasis={Boolean(o?.needs_review_orders)}
          hint={o ? `${fmt(o.pending_orders)} pending · ${fmt(o.calling_orders)} on a call now` : undefined}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Accounts by business type</CardTitle>
            <CardDescription>Which agent each account runs. Fixed when the account is created.</CardDescription>
          </CardHeader>
          <CardContent>
            {!o ? (
              <p className="text-sm text-muted-foreground" role="status">
                {error ? "Unavailable." : "Loading…"}
              </p>
            ) : verticalRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No accounts yet.</p>
            ) : (
              <ul className="space-y-4">
                {verticalRows.map((row) => (
                  <li key={row.key}>
                    <div className="flex items-baseline justify-between gap-3">
                      <Link
                        href={`/admin/merchants?vertical=${encodeURIComponent(row.key)}`}
                        className="min-w-0 truncate text-sm font-semibold hover:text-primary hover:underline"
                      >
                        {row.label}
                      </Link>
                      <span className="text-sm font-semibold tabular-nums">
                        {fmt(row.count)}
                        <span className="sr-only"> accounts</span>
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-tint" aria-hidden="true">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: row.count ? `${Math.max(3, (row.count / maxVertical) * 100)}%` : "0%" }}
                      />
                    </div>
                    {row.description && <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{row.description}</p>}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Quick links</CardTitle>
            <CardDescription>Common admin tasks.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <QuickLink href="/admin/merchants?create=1" icon={Plus} title="Create account" detail="Set up a new business with its agent, region and plan." />
            <QuickLink
              href="/admin/inquiries"
              icon={Inbox}
              title="Sales inquiries"
              detail={
                newInquiries === null
                  ? "Leads from the website's Talk to sales form."
                  : newInquiries === 0
                    ? "No new inquiries — you're all caught up."
                    : `${newInquiries.toLocaleString("en-US")} new ${newInquiries === 1 ? "inquiry" : "inquiries"} waiting for a reply.`
              }
              count={newInquiries ?? 0}
            />
            <QuickLink
              href="/admin/orders?status=needs_review"
              icon={ClipboardList}
              title="Records needing review"
              detail="Calls the agent couldn't settle on its own."
            />
            <QuickLink href="/admin/calls" icon={PhoneCall} title="Latest calls & chats" detail="Transcripts and recordings across every account." />
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function QuickLink({
  href,
  icon: Icon,
  title,
  detail,
  count = 0,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  detail: string;
  count?: number;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-3 rounded-md border border-border p-3 transition-colors hover:border-tint-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-sm font-semibold">
          {title}
          {count > 0 && (
            <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-bold leading-none text-primary-foreground">{count > 99 ? "99+" : count}</span>
          )}
        </span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{detail}</span>
      </span>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden="true" />
    </Link>
  );
}
