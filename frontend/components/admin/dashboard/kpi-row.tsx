import { Building2, Clock, PhoneCall, Radio } from "lucide-react";

import { KpiTile } from "@/components/admin/stats";
import { fmtInt } from "@/components/admin/numbers";

import type { DashboardData } from "./use-dashboard";

/** The headline figures: what is happening now and today. */
export function KpiRow({ data }: { data: DashboardData }) {
  const o = data.overview;
  const inactive = o ? Math.max(0, o.merchants - o.active_merchants) : 0;
  return (
    <section aria-label="Today" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <KpiTile
        label="Live calls"
        icon={Radio}
        href="/admin/live"
        value={fmtInt(data.live)}
        hint={data.live ? "On a call right now" : "No calls in progress"}
      />
      <KpiTile
        label="Calls today"
        icon={PhoneCall}
        href="/admin/calls"
        value={fmtInt(o?.calls_today)}
        hint={o ? `${fmtInt(o.inbound_today)} inbound · ${fmtInt(o.booked_today)} booked · ${fmtInt(o.confirmed_today)} confirmed` : undefined}
      />
      <KpiTile label="Minutes today" icon={Clock} value={fmtInt(o?.minutes_today)} hint="Phone minutes, every account" />
      <KpiTile
        label="Accounts"
        icon={Building2}
        href="/admin/merchants"
        value={fmtInt(o?.merchants)}
        hint={o ? (inactive ? `${fmtInt(o.active_merchants)} active · ${fmtInt(inactive)} inactive` : "All active") : undefined}
      />
    </section>
  );
}
