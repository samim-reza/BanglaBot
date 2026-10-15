"use client";

/** Sticky bar under the editor: status, conflict notice, Reset / Discard / Save. */

import { LoaderCircle, RefreshCw, RotateCcw, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { AgentFlowState } from "./use-agent-flow";

export function FlowSaveBar({ state }: { state: AgentFlowState }) {
  const { dirty, saving, saveError, conflict, discard, save, reset, reload } = state;

  const confirmReset = () => {
    if (window.confirm("Reset every step and line to the defaults?")) void reset();
  };

  return (
    <div className="sticky bottom-0 z-30 -mx-4 space-y-2 border-t border-border bg-card/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6 lg:-mx-8 lg:px-8">
      {conflict && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
          <span className="flex items-center gap-2">
            <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
            Changed somewhere else.
          </span>
          <Button type="button" size="sm" variant="outline" onClick={() => void reload()}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Reload
          </Button>
        </div>
      )}
      {saveError && !conflict && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {saveError}
        </p>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {saving ? (
            "Saving…"
          ) : dirty ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-300">
              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
              Unsaved changes
            </span>
          ) : null}
        </p>
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={confirmReset} disabled={saving}>
            Reset to defaults
          </Button>
          {dirty && (
            <Button type="button" variant="ghost" size="sm" onClick={discard} disabled={saving}>
              <RotateCcw className="h-3.5 w-3.5" aria-hidden />
              Discard
            </Button>
          )}
          <Button type="button" size="sm" onClick={() => void save()} disabled={!dirty || saving || conflict}>
            {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
