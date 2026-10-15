"use client";

/** A sample conversation for the selected branch: what the agent says, in order (agent lines only). */

import { Bot, LoaderCircle } from "lucide-react";

import { InfoTip } from "@/components/portal/kit";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { AgentFlowPreview, Direction } from "@/services/api";

const LANGUAGE_NAMES: Record<string, string> = { en: "English", bn: "Bangla" };

/** "{doctor}" placeholders shown as chips. */
function Said({ text }: { text: string }) {
  const parts = text.split(/(\{[a-z_][a-z0-9_]*\})/g);
  return (
    <>
      {parts.map((part, index) =>
        /^\{[a-z_][a-z0-9_]*\}$/.test(part) ? (
          <span key={index} className="rounded bg-card/70 px-1 font-mono text-[11.5px] text-muted-foreground">
            {part}
          </span>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

function Bubble({ label, text }: { label?: string; text: string }) {
  return (
    <li className="max-w-[92%] space-y-1">
      {label && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>}
      <p className="rounded-lg rounded-tl-sm bg-accent px-3 py-2 text-sm leading-relaxed text-accent-foreground">
        <Said text={text} />
      </p>
    </li>
  );
}

export function PreviewPane({
  preview,
  error,
  loading,
  direction,
  branchKey,
}: {
  preview: AgentFlowPreview | null;
  error: string | null;
  loading: boolean;
  direction: Direction;
  branchKey: string;
}) {
  const view = preview?.directions[direction];
  const branch = view?.branches.find((item) => item.key === branchKey) ?? view?.branches[0];
  const lines = branch?.steps.filter((step) => step.says.trim()) ?? [];

  return (
    <section aria-labelledby="flow-preview-title" className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h2 id="flow-preview-title" className="flex items-center gap-2 text-sm font-semibold">
          <Bot className="h-4 w-4 text-primary" aria-hidden />
          Preview
          <InfoTip label="About the preview">What your agent says in this branch, in order. Details like {"{doctor}"} are filled in on the call.</InfoTip>
        </h2>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          {loading && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-label="Updating" />}
          {preview && <span className="rounded-full bg-secondary px-2 py-0.5 font-semibold">{LANGUAGE_NAMES[preview.language] ?? preview.language}</span>}
        </span>
      </div>
      <div className={cn("px-4 py-4 transition-opacity", loading && preview && "opacity-60")}>
        {error && <p className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>}
        {!preview && !error ? (
          <div className="space-y-2" aria-busy="true" aria-label="Loading preview">
            {[0, 1, 2].map((key) => (
              <div key={key} className="h-10 w-4/5 animate-pulse rounded-lg bg-secondary" />
            ))}
          </div>
        ) : view ? (
          <ol className="space-y-3" aria-label={branch ? t(branch.label, branch.key) : "Conversation"}>
            {view.opening && <Bubble text={view.opening} />}
            {lines.map((step, index) => (
              <Bubble key={`${step.skill}-${index}`} label={t(step.label, step.skill)} text={step.says} />
            ))}
            {!view.opening && lines.length === 0 && <li className="text-sm text-muted-foreground">Nothing to show.</li>}
          </ol>
        ) : null}
      </div>
    </section>
  );
}
