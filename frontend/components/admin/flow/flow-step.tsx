"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Lock } from "lucide-react";

import { Pill } from "@/components/admin/badges";
import { Toggle } from "@/components/agent-flow/bits";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";

import { editable, type FlowControls } from "./controls";
import { appliedValue, describeValue, enabledPath, optionPath, ownerValue } from "./flow-paths";
import { FlowSetting } from "./flow-setting";
import { LockButton } from "./lock-button";
import { OptionControl } from "./option-control";
import { StepLines } from "./step-lines";

const KIND_LABELS: Record<string, string> = { gate: "Yes/no", router: "Router", effect: "After call", line: "Line", global: "Any time", readback: "Read-back" };

/** One step: on/off (+ lock) in the header; options (each lockable) and its lines when expanded. */
export function FlowStep({ skillKey, number, controls }: { skillKey: string; number?: number; controls: FlowControls }) {
  const [open, setOpen] = useState(false);
  const skill = controls.state.index.skills[skillKey];
  if (!skill) return null;
  const label = t(skill.label, skill.key);
  const onPath = enabledPath(skillKey);
  const enabled = skill.toggleable ? Boolean(appliedValue(controls.state, onPath)) : true;
  const locks = Object.keys(controls.state.locks).filter((path) => path.startsWith(`steps.${skillKey}.`));
  const expandable = skill.options.length > 0 || skill.lines.length > 0;
  const ownerOn = ownerValue(controls.saved, onPath);

  return (
    <li className={cn("rounded-lg border border-border bg-card", !enabled && "bg-surface")}>
      <div className="flex items-center gap-2 p-2.5">
        {number !== undefined && (
          <span
            aria-hidden="true"
            className={cn(
              "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11.5px] font-bold tabular-nums",
              enabled ? "bg-accent text-accent-foreground" : "bg-secondary text-muted-foreground",
            )}
          >
            {number}
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          disabled={!expandable}
          aria-expanded={expandable ? open : undefined}
          className="flex min-w-0 flex-1 items-center gap-1.5 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default"
        >
          {expandable ? (
            open ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <span className={cn("truncate text-sm font-semibold", !enabled && "text-muted-foreground")} title={t(skill.description) || undefined}>
            {label}
          </span>
          {KIND_LABELS[skill.kind] && <Pill className="px-2 py-0 text-[11px]">{KIND_LABELS[skill.kind]}</Pill>}
          {locks.length > 0 && <Lock className="h-3 w-3 shrink-0 text-[#92400e] dark:text-amber-300" aria-label={`${locks.length} locked`} />}
        </button>
        {skill.toggleable ? (
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
      {controls.errors[onPath] && <p className="px-3 pb-2 text-xs font-medium text-destructive">{controls.errors[onPath]}</p>}
      {open && expandable && (
        <div className="space-y-1 border-t border-border p-2">
          {skill.options.map((spec) => {
            const path = optionPath(skillKey, spec.key);
            const owner = ownerValue(controls.saved, path);
            return (
              <FlowSetting
                key={spec.key}
                label={t(spec.label, spec.key)}
                hint={t(spec.help) || undefined}
                owner={owner === undefined ? undefined : describeValue(owner, spec)}
                locked={path in controls.state.locks}
                canLock={controls.canLock}
                error={controls.errors[path]}
                onToggleLock={() => controls.toggleLock(path)}
              >
                <OptionControl
                  spec={spec}
                  value={appliedValue(controls.state, path)}
                  disabled={!editable(controls, path)}
                  onChange={(value) => controls.setValue(path, value)}
                />
              </FlowSetting>
            );
          })}
          <StepLines skill={skill} controls={controls} />
        </div>
      )}
    </li>
  );
}
