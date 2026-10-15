"use client";

import Link from "next/link";

import { useAdminMeta, verticalName } from "@/components/admin/use-admin-meta";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AdminOverview } from "@/services/api";

/** Accounts per business engine — one series, one hue; zero rows included so gaps show. */
export function AccountsByType({ overview }: { overview: AdminOverview | null }) {
  const { meta } = useAdminMeta();
  const keys = meta?.verticals.map((spec) => spec.key as string) ?? [];
  for (const key of Object.keys(overview?.by_vertical ?? {})) if (!keys.includes(key)) keys.push(key);
  const rows = overview ? keys.map((key) => ({ key, label: verticalName(meta, key), count: overview.by_vertical?.[key] ?? 0 })) : [];
  const max = Math.max(1, ...rows.map((row) => row.count));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Accounts by business type</CardTitle>
      </CardHeader>
      <CardContent>
        {!overview ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading…
          </p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No accounts yet.</p>
        ) : (
          <ul className="space-y-3">
            {rows.map((row) => (
              <li key={row.key}>
                <div className="flex items-baseline justify-between gap-3">
                  <Link href={`/admin/merchants?vertical=${encodeURIComponent(row.key)}`} className="min-w-0 truncate text-sm font-medium hover:text-primary hover:underline">
                    {row.label}
                  </Link>
                  <span className="text-sm font-semibold tabular-nums">
                    {row.count.toLocaleString("en-US")}
                    <span className="sr-only"> accounts</span>
                  </span>
                </div>
                <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-tint" aria-hidden="true">
                  <div className="h-full rounded-full bg-primary" style={{ width: row.count ? `${Math.max(3, (row.count / max) * 100)}%` : "0%" }} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
