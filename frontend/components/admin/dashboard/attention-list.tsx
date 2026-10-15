import Link from "next/link";
import { ArrowRight, ClipboardList, Inbox, Puzzle, UserCheck } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { DashboardData } from "./use-dashboard";

type Item = { href: string; icon: React.ComponentType<{ className?: string }>; title: string; count: number | null };

/** What is waiting for a person: records the agent couldn't settle, add-on requests, new leads. */
export function AttentionList({ data }: { data: DashboardData }) {
  const o = data.overview;
  const items: Item[] = [
    ...(data.signups !== null ? [{ href: "/admin/signups", icon: UserCheck, title: "Signups to approve", count: data.signups }] : []),
    { href: "/admin/orders?status=needs_review", icon: ClipboardList, title: "Records to review", count: o?.needs_review_orders ?? null },
    { href: "/admin/requests", icon: Puzzle, title: "Add-on requests", count: o?.pending_addon_requests ?? null },
    { href: "/admin/inquiries?status=new", icon: Inbox, title: "New sales inquiries", count: data.newInquiries },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Needs attention</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="group flex items-center gap-3 rounded-md border border-border p-3 transition-colors hover:border-tint-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
              <item.icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1 text-sm font-semibold">{item.title}</span>
            <span className={item.count ? "text-lg font-semibold" : "text-lg font-semibold text-muted-foreground"}>
              {item.count === null ? "—" : item.count > 100 ? "100+" : item.count.toLocaleString("en-US")}
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden="true" />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
