"use client";

import { useCallback, useState } from "react";

import { usePolling } from "@/components/admin/use-polling";
import { formatApiError } from "@/services/api";
import { systemApi, type VoiceEngine } from "@/services/api/admin/system";

/** The voice engine's state, refreshed every 10 s while visible. */
export function useVoiceEngine() {
  const [engine, setEngine] = useState<VoiceEngine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setEngine(await systemApi.voiceEngine());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load the voice engine."));
    } finally {
      setRefreshing(false);
    }
  }, []);

  usePolling(load, 10_000);
  return { engine, error, refreshing, reload: load };
}
