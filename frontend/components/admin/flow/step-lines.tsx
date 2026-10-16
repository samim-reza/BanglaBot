"use client";

import { Pill } from "@/components/admin/badges";
import type { FlowSkill } from "@/services/api/agentFlow";

import type { FlowControls } from "./controls";

/** What the step says, read-only (owners reword lines in their portal). */
export function StepLines({ skill, controls }: { skill: FlowSkill; controls: FlowControls }) {
  if (!skill.lines.length) return null;
  const effective = controls.state.index.effective.steps[skill.key]?.lines ?? {};
  const owner = controls.saved.steps?.[skill.key]?.lines ?? {};
  return (
    <div className="space-y-2 px-2 pt-2">
      <p className="text-xs font-semibold text-muted-foreground">Says</p>
      <ul className="space-y-1.5">
        {skill.lines.map((spec) => {
          const text = effective.en?.[spec.key] || spec.default.en || Object.values(spec.default)[0] || "";
          const edited = Boolean(owner.en?.[spec.key]);
          return (
            <li key={spec.key} className="rounded-md bg-surface px-2.5 py-1.5 text-[13px]">
              <span className="mr-2 text-xs text-muted-foreground">{spec.label}</span>
              {edited && (
                <Pill tone="blue" className="mr-1.5 px-1.5 py-0 text-[10.5px]">
                  Edited
                </Pill>
              )}
              <span className="italic">“{text}”</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
