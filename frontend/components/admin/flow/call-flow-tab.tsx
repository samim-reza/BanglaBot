"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { useAdminMe } from "@/components/admin/shell/admin-me";
import { LoadingRows } from "@/components/admin/states";
import { Segments } from "@/components/agent-flow/bits";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import type { Direction } from "@/services/api";

import type { FlowControls } from "./controls";
import { BranchSection, StepGroup } from "./flow-section";
import { SaveBar } from "@/components/admin/save-bar";
import { useAdminFlow } from "./use-admin-flow";

/** The account's call flow: branches → steps with what calls use, the owner's value and locks. */
export function CallFlowTab({ merchantId }: { merchantId: string }) {
  const flow = useAdminFlow(merchantId);
  const { can } = useAdminMe();
  const toast = useAppToast();
  const directions = (["inbound", "outbound"] as Direction[]).filter((key) => flow.flow?.directions[key]);
  const [picked, setPicked] = useState<Direction | null>(null);
  const direction = picked && directions.includes(picked) ? picked : directions[0];

  if (flow.loading && !flow.flow) return <LoadingRows label="Loading the call flow…" rows={6} />;
  if (flow.fixed) return <EmptyState title="Fixed call flow">This business type has no editable steps.</EmptyState>;
  if (!flow.flow || !flow.state || !direction) return <ApiError message={flow.error ?? "Could not load the call flow."} />;

  const view = flow.flow.directions[direction]!;
  const bp = view.blueprint;
  const controls: FlowControls = {
    state: flow.state,
    saved: flow.flow.config ?? {},
    canEdit: can("editFlow"),
    canLock: can("lockFlow"),
    errors: flow.fieldErrors,
    setValue: flow.setValue,
    toggleLock: flow.toggleLock,
  };
  const always = [...new Set([...bp.line_skills, ...bp.prelude])];
  const lockCount = Object.keys(flow.state.locks).length;

  const save = async () => {
    if (await flow.save()) toast.success("Call flow saved.");
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {directions.length > 1 ? (
          <Segments
            label="Direction"
            value={direction}
            options={directions.map((key) => ({ value: key, label: key === "inbound" ? "Inbound" : "Outbound" }))}
            onChange={setPicked}
          />
        ) : (
          <span className="text-sm font-semibold">{direction === "inbound" ? "Inbound" : "Outbound"}</span>
        )}
        <span className="text-xs text-muted-foreground" title="Locked settings apply on calls and the owner can't change them">
          {lockCount} locked · owner plan: {flow.flow.editing === "lines" ? "wording only" : "full editing"}
        </span>
      </div>

      <ApiError message={flow.error} />
      {flow.conflict && (
        <Button variant="outline" size="sm" onClick={() => void flow.reload()}>
          <RefreshCw className="h-3.5 w-3.5" />
          Reload latest
        </Button>
      )}

      <StepGroup title="Always" keys={always} controls={controls} />
      <StepGroup title="Any time" keys={bp.globals} controls={controls} />
      <div className="space-y-3">
        {bp.branches.map((branch) => (
          <BranchSection key={branch.key} branch={branch} controls={controls} />
        ))}
      </div>
      <StepGroup title="After the call" keys={bp.effects} controls={controls} />

      <SaveBar dirty={flow.dirty} saving={flow.saving} onSave={() => void save()} onDiscard={flow.discard} />
    </div>
  );
}
