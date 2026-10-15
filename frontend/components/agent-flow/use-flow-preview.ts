"use client";

/** The sample conversation for the current draft, refreshed shortly after each edit. */

import { useEffect, useRef, useState } from "react";

import { agentFlowApi, flowErrors, formatApiError, type AgentFlowPreview, type FlowConfig } from "@/services/api";

import { canon } from "./model";

const DEBOUNCE_MS = 600;

export function useFlowPreview(config: FlowConfig | null) {
  const [preview, setPreview] = useState<AgentFlowPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);
  const key = config ? canon(config) : "";

  useEffect(() => {
    if (!key) return;
    const ticket = ++latest.current;
    const body = JSON.parse(key) as FlowConfig;
    const timer = window.setTimeout(() => {
      setLoading(true);
      agentFlowApi
        .preview(body)
        .then((next) => {
          if (ticket !== latest.current) return;
          setPreview(next);
          setError(null);
        })
        .catch((err) => {
          if (ticket !== latest.current) return;
          setError(flowErrors(err) ? "Fix the marked settings to see the preview." : formatApiError(err, "Preview unavailable."));
        })
        .finally(() => {
          if (ticket === latest.current) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [key]);

  return { preview, error, loading };
}
