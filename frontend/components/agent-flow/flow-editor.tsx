"use client";

/** The call-flow editor: direction, branch tabs, ordered steps, fixed groups, preview, drawer, save bar. */

import { useState } from "react";
import { Sparkles } from "lucide-react";
import Link from "next/link";

import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import type { Direction, FlowBlueprint } from "@/services/api";

import { Gate, Segments } from "./bits";
import { BranchHeader, BranchTabs } from "./branch-tabs";
import { FlowSaveBar } from "./flow-save-bar";
import { PreviewPane } from "./preview-pane";
import { UPGRADE_LINES_ONLY } from "./rules";
import { StepDrawer } from "./step-drawer";
import { BranchSteps, SkillGroup, type ReadyFlow } from "./step-list";
import { useFlowPreview } from "./use-flow-preview";

function firstBranch(blueprint: FlowBlueprint | undefined): string {
  if (!blueprint) return "";
  return blueprint.branches.some((branch) => branch.key === blueprint.default_branch) ? String(blueprint.default_branch) : blueprint.branches[0]?.key ?? "";
}

/** Greeting first, then the opening question (prelude), then goodbye / read-back lines. */
function openingKeys(blueprint: FlowBlueprint): string[] {
  const lines = blueprint.line_skills;
  return lines.includes("greet") ? ["greet", ...blueprint.prelude, ...lines.filter((key) => key !== "greet")] : [...blueprint.prelude, ...lines];
}

export function FlowEditor({ state }: { state: ReadyFlow }) {
  const { vertical } = useWorkspace();
  const directions = (["inbound", "outbound"] as Direction[]).filter((key) => state.model.blueprints[key]);
  const [direction, setDirection] = useState<Direction>(directions[0] ?? "inbound");
  const blueprint = state.model.blueprints[direction];
  const [branchKey, setBranchKey] = useState(() => firstBranch(blueprint));
  const [open, setOpen] = useState<string | null>(null);
  const preview = useFlowPreview(state.config);

  if (!blueprint) return null;
  const branch = blueprint.branches.some((item) => item.key === branchKey) ? branchKey : firstBranch(blueprint);
  const switchDirection = (next: Direction) => {
    setDirection(next);
    setBranchKey(firstBranch(state.model.blueprints[next]));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {directions.length > 1 ? (
          <Segments<Direction>
            label="Call direction"
            value={direction}
            onChange={switchDirection}
            options={[
              { value: "inbound", label: "Calls in" },
              { value: "outbound", label: `${t(vertical.outbound_label, "Call")}s out` },
            ]}
          />
        ) : (
          <span />
        )}
        {state.model.editing === "lines" && (
          <Gate reason={UPGRADE_LINES_ONLY}>
            <Link href="/plan" className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground hover:underline">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
              Lines only · Upgrade
            </Link>
          </Gate>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <section aria-label="Steps" className="space-y-3">
            {blueprint.branches.length > 1 && <BranchTabs branches={blueprint.branches} active={branch} enabled={state.draft.branches} onSelect={setBranchKey} />}
            <BranchHeader state={state} branchKey={branch} />
            <BranchSteps state={state} branchKey={branch} onOpen={setOpen} />
          </section>
          <SkillGroup state={state} title="Greeting & goodbye" keys={openingKeys(blueprint)} onOpen={setOpen} />
          <SkillGroup state={state} title="Always on" info="Handled at any point of the call, or right after it." keys={[...blueprint.globals, ...blueprint.effects]} onOpen={setOpen} />
        </div>
        <aside className="h-fit lg:sticky lg:top-[77px]">
          <PreviewPane preview={preview.preview} error={preview.error} loading={preview.loading} direction={direction} branchKey={branch} />
        </aside>
      </div>

      <FlowSaveBar state={state} />
      {open && <StepDrawer state={state} skillKey={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
