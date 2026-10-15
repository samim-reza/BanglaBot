"use client";

import { useCallback, useEffect, useState } from "react";

import { formatApiError } from "@/services/api";
import { financeApi, type FinanceForecast, type FinanceOverview } from "@/services/api/admin/finance";

/** The month's overview and month-end forecast. Holds the previous figures while a new month loads. */
export function useFinanceOverview(month: string) {
  const [overview, setOverview] = useState<FinanceOverview | null>(null);
  const [forecast, setForecast] = useState<FinanceForecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [o, f] = await Promise.allSettled([financeApi.overview(month), financeApi.forecast(month)]);
    if (o.status === "fulfilled") setOverview(o.value);
    if (f.status === "fulfilled") setForecast(f.value);
    setError(o.status === "rejected" ? formatApiError(o.reason, "Could not load finance.") : null);
    setLoading(false);
  }, [month]);

  useEffect(() => {
    void load();
  }, [load]);

  return { overview, forecast, error, loading, reload: load };
}
