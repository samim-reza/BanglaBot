"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, CheckCircle2, ClipboardList, PhoneCall } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { PageHeader, StatTile } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { humanize } from "@/lib/format";
import { adminApi, formatApiError, type AdminOverview } from "@/services/api";

const PRIMARY: Array<{ key: keyof AdminOverview & string; label: string; icon: typeof Building2; accent?: string }> = [
  { key: "merchants", label: "Merchants", icon: Building2 },
  { key: "orders", label: "Orders", icon: ClipboardList },
  { key: "calls_today", label: "Calls today", icon: PhoneCall, accent: "text-[#1d4ed8] dark:text-blue-300" },
  { key: "confirmed_today", label: "Confirmed today", icon: CheckCircle2, accent: "text-[#065f46] dark:text-emerald-300" },
];

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .overview()
      .then((data) => {
        setOverview(data);
        setError(null);
      })
      .catch((err) => setError(formatApiError(err, "Could not load the overview.")));
  }, []);

  const primaryKeys = new Set<string>(PRIMARY.map((item) => item.key));
  const extra = overview
    ? Object.entries(overview).filter(([key, value]) => !primaryKeys.has(key) && typeof value === "number")
    : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        subtitle="Platform-wide activity across every merchant."
        actions={
          <Button asChild variant="outline">
            <Link href="/admin/merchants">Manage merchants</Link>
          </Button>
        }
      />
      <ApiError message={error} />
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {PRIMARY.map((item) => (
          <StatTile key={item.key} label={item.label} value={overview ? overview[item.key] ?? 0 : "—"} icon={item.icon} accent={item.accent} />
        ))}
        {extra.map(([key, value]) => (
          <StatTile key={key} label={humanize(key)} value={value} />
        ))}
      </section>
    </div>
  );
}
