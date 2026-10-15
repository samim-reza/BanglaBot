"use client";

import { useCallback, useState } from "react";

import { usePolling } from "@/components/admin/use-polling";
import { adminApi, formatApiError } from "@/services/api";
import { dashboardApi, type DashboardOverview } from "@/services/api/admin/dashboard";
import { financeOverviewOrNull, type FinanceOverview } from "@/services/api/admin/finance";
import { signupsToApprove } from "@/components/admin/shell/use-nav-badges";
import { systemApi, type SystemHealth, type VoiceEngine } from "@/services/api/admin/system";

export type DashboardData = {
  overview: DashboardOverview | null;
  live: number | null;
  engine: VoiceEngine | null;
  health: SystemHealth | null;
  /** null for roles without finance. */
  finance: FinanceOverview | null;
  newInquiries: number | null;
  /** null for roles that can't review signups. */
  signups: number | null;
};

const EMPTY: DashboardData = { overview: null, live: null, engine: null, health: null, finance: null, newInquiries: null, signups: null };

const none = async () => null;

/** Everything the dashboard shows: live calls every 5 s, the rest every 30 s, while the tab is visible.
 * Finance and signups load only for roles that can see them. */
export function useDashboard({ finance: canFinance, signups: canSignups, ready }: { finance: boolean; signups: boolean; ready: boolean }) {
  const [data, setData] = useState<DashboardData>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    const [overview, engine, health, finance, inquiries, signups] = await Promise.allSettled([
      dashboardApi.overview(),
      systemApi.voiceEngine(),
      systemApi.health(),
      canFinance ? financeOverviewOrNull() : none(),
      adminApi.inquiries({ status: "new", page_size: 1 }),
      canSignups ? signupsToApprove() : none(),
    ]);
    setData((current) => ({
      ...current,
      overview: overview.status === "fulfilled" ? overview.value : current.overview,
      engine: engine.status === "fulfilled" ? engine.value : current.engine,
      health: health.status === "fulfilled" ? health.value : current.health,
      live: health.status === "fulfilled" && current.live === null ? health.value.live_calls : current.live,
      finance: finance.status === "fulfilled" ? finance.value : current.finance,
      newInquiries: inquiries.status === "fulfilled" ? inquiries.value.total : current.newInquiries,
      signups: signups.status === "fulfilled" ? signups.value : current.signups,
    }));
    setError(overview.status === "rejected" ? formatApiError(overview.reason, "Could not load the dashboard.") : null);
    setRefreshing(false);
  }, [canFinance, canSignups]);

  const loadLive = useCallback(async () => {
    const result = await systemApi.liveCalls();
    setData((current) => ({ ...current, live: result.total }));
  }, []);

  // Waits for the admin's role so the first load already includes (or skips) the role-only figures.
  usePolling(loadAll, 30_000, ready);
  usePolling(loadLive, 5_000);

  return { data, error, refreshing, refresh: loadAll };
}
