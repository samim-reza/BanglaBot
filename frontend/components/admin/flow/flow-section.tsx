"use client";

import { ListOrdered } from "lucide-react";

import { Toggle } from "@/components/agent-flow/bits";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { FlowBranch } from "@/services/api/agentFlow";

import { editable, type FlowControls } from "./controls";
import { appliedValue, branchPath, describeValue, orderPath, ownerValue } from "./flow-paths";
import { FlowStep } from "./flow-step";
import { LockButton } from "./lock-button";

/** A fixed group of steps (always-on lines, any-time skills, after-call effects). */
export function StepGroup({ title, keys, controls, numbered }: { title: string; keys: string[]; controls: FlowControls; numbered?: boolean }) {
  if (!keys.length) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      <ol className="space-y-2">
        {keys.map((key, i) => (
          <FlowStep key={key} skillKey={key} number={numbered ? i + 1 : undefined} controls={controls} />
        ))}
      </ol>
    </section>
  );
}

/** A branch of the call (book, cancel, …): on/off + lock, its step order (lockable) and steps. */
export function BranchSection({ branch, controls }: { branch: FlowBranch; controls: FlowControls }) {
  const onPath = branchPath(branch.key);
  const order = orderPath(branch.key);
  const enabled = branch.toggleable ? Boolean(appliedValue(controls.state, onPath)) : true;
  const steps = (appliedValue(controls.state, order) as string[] | undefined) ?? branch.skills;
  const ownerOn = ownerValue(controls.saved, onPath);
  const label = t(branch.label, branch.key);

  return (
    <section className={cn("space-y-2 rounded-lg border border-border p-3", !enabled && "bg-surface")}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className={cn("min-w-0 flex-1 text-sm font-semibold", !enabled && "text-muted-foreground")}>{label}</h3>
        <span className="flex items-center gap-1" title="Lock the step order">
          <ListOrdered className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <LockButton locked={order in controls.state.locks} canLock={controls.canLock} onToggle={() => controls.toggleLock(order)} label={`${label} step order`} />
        </span>
        {branch.toggleable ? (
          <>
            <span className="hidden text-xs text-muted-foreground sm:inline" title="The owner's own setting">
              Owner: {ownerOn === undefined ? "default" : describeValue(ownerOn)}
            </span>
            <Toggle checked={enabled} onChange={(value) => controls.setValue(onPath, value)} label={`${label} on`} disabled={!editable(controls, onPath)} />
            <LockButton locked={onPath in controls.state.locks} canLock={controls.canLock} onToggle={() => controls.toggleLock(onPath)} label={`${label} on/off`} />
          </>
        ) : (
          <span className="text-xs text-muted-foreground">Always on</span>
        )}
      </div>
      {(controls.errors[onPath] || controls.errors[order]) && (
        <p className="text-xs font-medium text-destructive">{controls.errors[onPath] || controls.errors[order]}</p>
      )}
      <ol className="space-y-2">
        {steps.map((key, i) => (
          <FlowStep key={key} skillKey={key} number={i + 1} controls={controls} />
        ))}
      </ol>
    </section>
  );
}
