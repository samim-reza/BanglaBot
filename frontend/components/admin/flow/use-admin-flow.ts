"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { formatApiError, isApiRequestError } from "@/services/api";
import { flowErrors, type FlowConfig } from "@/services/api/agentFlow";
import { adminFlowApi, type AdminAgentFlow, type FlowLocks } from "@/services/api/admin/flow";

import { appliedValue, canon, indexFlow, withOwnerValue, type FlowState } from "./flow-paths";

/**
 * Load an account's flow, keep a draft of the owner settings and the lock map, and save both:
 * settings first (with the loaded hash, so a concurrent owner edit answers 409), then locks.
 */
export function useAdminFlow(merchantId: string) {
  const [flow, setFlow] = useState<AdminAgentFlow | null>(null);
  const [config, setConfig] = useState<FlowConfig>({});
  const [locks, setLocks] = useState<FlowLocks>({});
  const [loading, setLoading] = useState(true);
  const [fixed, setFixed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminFlowApi.get(merchantId);
      setFlow(data);
      setConfig(data.config ?? {});
      setLocks(data.locks ?? {});
      setError(null);
      setConflict(false);
      setFieldErrors({});
      setFixed(false);
    } catch (err) {
      if (isApiRequestError(err) && err.status === 404 && /fixed call flow/i.test(err.detail)) setFixed(true);
      else setError(formatApiError(err, "Could not load the call flow."));
    } finally {
      setLoading(false);
    }
  }, [merchantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const index = useMemo(() => (flow ? indexFlow(flow) : null), [flow]);
  const state: FlowState | null = useMemo(
    () => (index && flow ? { index, config, locks, savedLocks: flow.locks ?? {} } : null),
    [index, flow, config, locks],
  );

  const configDirty = Boolean(flow) && canon(config) !== canon(flow?.config ?? {});
  const locksDirty = Boolean(flow) && canon(locks) !== canon(flow?.locks ?? {});

  /** Change a setting: a locked one changes its lock value, otherwise the owner's value. */
  const setValue = useCallback(
    (path: string, value: unknown) => {
      if (path in locks) setLocks((current) => ({ ...current, [path]: value }));
      else setConfig((current) => withOwnerValue(current, path, value));
    },
    [locks],
  );

  /** Lock at what calls currently use, or unlock (the owner's value applies again). */
  const toggleLock = useCallback(
    (path: string) => {
      if (!state) return;
      setLocks((current) => {
        if (path in current) {
          const next = { ...current };
          delete next[path];
          return next;
        }
        return { ...current, [path]: appliedValue(state, path) ?? null };
      });
    },
    [state],
  );

  const discard = useCallback(() => {
    if (!flow) return;
    setConfig(flow.config ?? {});
    setLocks(flow.locks ?? {});
    setFieldErrors({});
    setError(null);
  }, [flow]);

  const save = useCallback(async (): Promise<boolean> => {
    if (!flow) return false;
    setSaving(true);
    setFieldErrors({});
    setError(null);
    try {
      if (configDirty) {
        // Keep the new hash even if the lock save below fails, so a retry isn't a false 409.
        const saved = await adminFlowApi.save(merchantId, config, flow.hash);
        setFlow({ ...saved, locks: flow.locks ?? {} });
        setConfig(saved.config ?? {});
      }
      if (locksDirty) await adminFlowApi.saveLocks(merchantId, locks);
      await load();
      return true;
    } catch (err) {
      if (isApiRequestError(err) && err.status === 409) setConflict(true);
      const parsed = flowErrors(err);
      if (parsed) setFieldErrors(Object.fromEntries(parsed.errors.map((item) => [item.path, item.message])));
      setError(formatApiError(err, "Could not save the call flow."));
      return false;
    } finally {
      setSaving(false);
    }
  }, [flow, configDirty, locksDirty, merchantId, config, locks, load]);

  return { flow, state, loading, fixed, error, conflict, fieldErrors, saving, dirty: configDirty || locksDirty, setValue, toggleLock, discard, save, reload: load };
}
