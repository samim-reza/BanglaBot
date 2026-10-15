"use client";

/** Loads the call flow, keeps the draft, saves it as a sparse config (409 / 422 aware), resets it. */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useAppToast } from "@/components/app-toast";
import { agentFlowApi, flowErrors, formatApiError, isApiRequestError, type AgentFlow, type FlowConfig, type FlowFieldError } from "@/services/api";

import { buildConfig } from "./config";
import { buildModel, canon, revertPaths, under, type FlowDraft, type FlowModel } from "./model";

export type FlowStatus = "loading" | "ready" | "fixed" | "error";

export function useAgentFlow(enabled = true) {
  const toast = useAppToast();
  const [status, setStatus] = useState<FlowStatus>(enabled ? "loading" : "fixed");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [model, setModel] = useState<FlowModel | null>(null);
  const [draft, setDraftState] = useState<FlowDraft | null>(null);
  /** Locks learnt from a 422 on top of the ones the server listed. */
  const [extraLocks, setExtraLocks] = useState<string[]>([]);
  const [errors, setErrors] = useState<FlowFieldError[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);

  const adopt = useCallback((flow: AgentFlow) => {
    const next = buildModel(flow);
    setModel(next);
    setDraftState(next.initial);
    setExtraLocks([]);
    setErrors([]);
    setSaveError(null);
    setConflict(false);
    setStatus("ready");
  }, []);

  const load = useCallback(async () => {
    if (!enabled) return;
    setStatus((current) => (current === "ready" ? current : "loading"));
    try {
      adopt(await agentFlowApi.get());
      setLoadError(null);
    } catch (err) {
      if (isApiRequestError(err) && err.status === 404) {
        setStatus("fixed");
        return;
      }
      setLoadError(formatApiError(err, "Could not load your call flow."));
      setStatus("error");
    }
  }, [adopt, enabled]);

  useEffect(() => {
    void load();
  }, [load]);

  const locked = useMemo(() => [...(model?.locked ?? []), ...extraLocks], [model, extraLocks]);
  const config = useMemo<FlowConfig | null>(() => (model && draft ? buildConfig(model, draft, locked) : null), [model, draft, locked]);
  const saved = useMemo<FlowConfig | null>(() => (model ? buildConfig(model, model.initial, locked) : null), [model, locked]);
  const dirty = Boolean(config && saved && canon(config) !== canon(saved));

  /** Change the draft; `path` is what was edited, so its errors clear. */
  const update = useCallback((path: string, change: (draft: FlowDraft) => FlowDraft) => {
    setDraftState((current) => (current ? change(current) : current));
    setErrors((current) => current.filter((error) => !under(error.path, path) && !under(path, error.path)));
  }, []);

  const discard = useCallback(() => {
    if (!model) return;
    setDraftState(model.initial);
    setErrors([]);
    setSaveError(null);
  }, [model]);

  const save = useCallback(async () => {
    if (!model || !config) return;
    setSaving(true);
    setSaveError(null);
    try {
      adopt(await agentFlowApi.save(config, model.hash));
      toast.success("Saved");
    } catch (err) {
      if (isApiRequestError(err) && err.status === 409) {
        setConflict(true);
        return;
      }
      const problems = flowErrors(err);
      if (problems) {
        setErrors(problems.errors);
        if (problems.locked.length) {
          setExtraLocks((current) => [...new Set([...current, ...problems.locked])]);
          setDraftState((current) => (current ? revertPaths(current, model.initial, problems.locked) : current));
        }
        setSaveError(problems.errors.length === 1 ? problems.errors[0].message : `${problems.errors.length || "Some"} settings need a fix.`);
        return;
      }
      setSaveError(formatApiError(err, "Could not save your call flow."));
    } finally {
      setSaving(false);
    }
  }, [adopt, config, model, toast]);

  const reset = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      adopt(await agentFlowApi.reset());
      toast.success("Back to defaults");
    } catch (err) {
      setSaveError(formatApiError(err, "Could not reset your call flow."));
    } finally {
      setSaving(false);
    }
  }, [adopt, toast]);

  return { status, loadError, model, draft, locked, config, dirty, errors, saveError, conflict, saving, update, discard, save, reset, reload: load };
}

export type AgentFlowState = ReturnType<typeof useAgentFlow>;
