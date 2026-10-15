"use client";

import { useCallback, useState } from "react";

import { usePolling } from "@/components/admin/use-polling";
import { formatApiError } from "@/services/api";
import { systemApi, type SystemHealth } from "@/services/api/admin/system";

/** System health, refreshed every 10 s while visible. */
export function useHealth() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setHealth(await systemApi.health());
      setCheckedAt(new Date());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load system health."));
    } finally {
      setRefreshing(false);
    }
  }, []);

  usePolling(load, 10_000);
  return { health, error, checkedAt, refreshing, reload: load };
}
