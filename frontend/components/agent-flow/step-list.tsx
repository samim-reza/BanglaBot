"use client";

/** The ordered steps of a branch, and the fixed groups (greeting & goodbye, always on). */

import { InfoTip } from "@/components/portal/kit";
import { useWorkspace } from "@/lib/workspace";

import { StepCard, type StepMove } from "./step-card";
import { LOCKED_HINT, UPGRADE_LINES_ONLY, errorsFor, isLocked, lockedUnder, moveStep, stepNeedsUpgrade } from "./rules";
import { withStep } from "./model";
import type { AgentFlowState } from "./use-agent-flow";

type Ready = AgentFlowState & { model: NonNullable<AgentFlowState["model"]>; draft: NonNullable<AgentFlowState["draft"]> };

function StepRow({ state, skillKey, number, move, onOpen }: { state: Ready; skillKey: string; number?: number; move?: StepMove; onOpen: (key: string) => void }) {
  const { entitlements } = useWorkspace();
  const { model, draft, locked, config, errors, update } = state;
  const skill = model.skills[skillKey];
  const step = draft.steps[skillKey];
  if (!skill || !step) return null;
  const path = `steps.${skillKey}`;
  const upgrade = stepNeedsUpgrade(skillKey, entitlements.capabilities) && !step.enabled;
  const toggleReason =
    model.editing === "lines"
      ? UPGRADE_LINES_ONLY
      : isLocked(locked, `${path}.enabled`)
        ? LOCKED_HINT
        : upgrade
          ? "Not in your plan — upgrade to switch this on."
          : null;
  return (
    <StepCard
      skill={skill}
      number={number}
      enabled={step.enabled}
      edited={Boolean(config?.steps?.[skillKey])}
      locked={lockedUnder(locked, path)}
      errorCount={errorsFor(errors, path).length}
      toggleReason={toggleReason}
      move={move}
      onToggle={(value) => update(`${path}.enabled`, (current) => withStep(current, skillKey, (row) => ({ ...row, enabled: value })))}
      onOpen={() => onOpen(skillKey)}
    />
  );
}

export function BranchSteps({ state, branchKey, onOpen }: { state: Ready; branchKey: string; onOpen: (key: string) => void }) {
  const { model, draft, locked, update } = state;
  const branch = model.branches[branchKey];
  const order = draft.order[branchKey] ?? branch?.skills ?? [];
  if (!branch) return null;
  const reason = model.editing === "lines" ? UPGRADE_LINES_ONLY : isLocked(locked, `order.${branchKey}`) ? LOCKED_HINT : null;
  const setOrder = (next: string[] | null) =>
    next ? () => update(`order.${branchKey}`, (current) => ({ ...current, order: { ...current.order, [branchKey]: next } })) : null;
  return (
    <ol className="space-y-2" aria-label="Steps">
      {order.map((key, index) => {
        const move: StepMove = {
          movable: branch.movable.some((group) => group.includes(key)),
          reason,
          up: reason ? null : setOrder(moveStep(branch, order, index, -1)),
          down: reason ? null : setOrder(moveStep(branch, order, index, 1)),
        };
        return <StepRow key={key} state={state} skillKey={key} number={index + 1} move={move} onOpen={onOpen} />;
      })}
    </ol>
  );
}

export function SkillGroup({ state, title, info, keys, onOpen }: { state: Ready; title: string; info?: string; keys: string[]; onOpen: (key: string) => void }) {
  const shown = keys.filter((key) => state.model.skills[key]);
  if (!shown.length) return null;
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
        {info && <InfoTip label={`About ${title.toLowerCase()}`}>{info}</InfoTip>}
      </h3>
      <ul className="space-y-2">
        {shown.map((key) => (
          <StepRow key={key} state={state} skillKey={key} onOpen={onOpen} />
        ))}
      </ul>
    </section>
  );
}

export type { Ready as ReadyFlow };
