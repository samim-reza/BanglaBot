"use client";

import { useCallback, useEffect, useState } from "react";

import { usePolling } from "@/components/admin/use-polling";
import { formatApiError } from "@/services/api";
import { systemApi, type LiveCall } from "@/services/api/admin/system";

/** Calls in progress, polled every 3 s while the tab is visible; `elapsed` ticks the clocks in between. */
export function useLiveCalls() {
  const [items, setItems] = useState<LiveCall[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState(0);
  const [now, setNow] = useState(0);

  const load = useCallback(async () => {
    try {
      const result = await systemApi.liveCalls();
      setItems(result.items);
      setFetchedAt(Date.now());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load live calls."));
    } finally {
      setLoaded(true);
    }
  }, []);

  usePolling(load, 3_000);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(timer);
  }, []);

  const elapsed = fetchedAt && now > fetchedAt ? Math.floor((now - fetchedAt) / 1000) : 0;
  return { items, loaded, error, elapsed, reload: load };
}
