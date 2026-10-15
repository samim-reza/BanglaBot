"use client";

/** Read-only steps for business types whose call flow is fixed (no skill blueprint to edit). */

import { useEffect, useState } from "react";
import { Route } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { SectionCard } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, merchantApi, type FlowPreview } from "@/services/api";

function StepList({ title, steps }: { title: string; steps: string[] }) {
  return (
    <section className="min-w-0 rounded-md border border-border p-4" aria-label={title}>
      <h4 className="text-sm font-semibold">{title}</h4>
      {steps.length ? (
        <ol className="mt-3 space-y-2.5">
          {steps.map((step, index) => (
            <li key={`${index}-${step}`} className="flex gap-3 text-sm leading-relaxed">
              <span
                aria-hidden
                className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-accent-foreground tabular-nums"
              >
                {index + 1}
              </span>
              <span className="min-w-0">{step}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">No steps to show.</p>
      )}
    </section>
  );
}

export function LegacyFlow({ version }: { version: number }) {
  const { vertical } = useWorkspace();
  const [preview, setPreview] = useState<FlowPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    merchantApi
      .flowPreview()
      .then((next) => {
        if (cancelled) return;
        setPreview(next);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(formatApiError(err, "Could not load how your agent works."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [version, reload]);

  const inbound = preview?.sections?.inbound;
  const outbound = preview?.sections?.outbound;

  return (
    <SectionCard
      id="flow"
      icon={Route}
      title="How your agent works"
      description="Fixed for your business type."
    >
      {error ? (
        <div className="space-y-3">
          <ApiError message={error} />
          <Button type="button" variant="outline" size="sm" onClick={() => setReload((n) => n + 1)}>
            Try again
          </Button>
        </div>
      ) : loading && !preview ? (
        <div className="grid gap-4 md:grid-cols-2" aria-busy="true" aria-label="Loading">
          {[0, 1].map((key) => (
            <div key={key} className="h-48 animate-pulse rounded-md bg-secondary" />
          ))}
        </div>
      ) : (
        <div className={cn("grid gap-4 transition-opacity", loading && "opacity-60", inbound && outbound && "md:grid-cols-2")}>
          {inbound && <StepList title="Customer contacts you" steps={inbound} />}
          {outbound && <StepList title={t(vertical.outbound_label, "Outbound call")} steps={outbound} />}
          {!inbound && !outbound && <p className="text-sm text-muted-foreground">No preview available.</p>}
        </div>
      )}
    </SectionCard>
  );
}
