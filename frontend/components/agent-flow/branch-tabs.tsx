"use client";

/** What a caller can want (new booking, move, cancel …): tabs, and the on/off for the open one. */

import { useRef, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { FlowBranch } from "@/services/api";

import { FieldErrors, Gate, LockBadge, Toggle } from "./bits";
import { LOCKED_HINT, UPGRADE_LINES_ONLY, errorsFor, isLocked } from "./rules";
import type { ReadyFlow } from "./step-list";

export function BranchTabs({ branches, active, enabled, onSelect }: { branches: FlowBranch[]; active: string; enabled: Record<string, boolean>; onSelect: (key: string) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = branches.findIndex((branch) => branch.key === active);
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = branches[(index + step + branches.length) % branches.length].key;
    onSelect(next);
    refs.current[next]?.focus();
  };
  return (
    <div role="tablist" aria-label="What callers want" className="flex gap-1 overflow-x-auto border-b border-border">
      {branches.map((branch) => {
        const selected = branch.key === active;
        return (
          <button
            key={branch.key}
            ref={(node) => {
              refs.current[branch.key] = node;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(branch.key)}
            onKeyDown={onKeyDown}
            className={cn(
              "-mb-px inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              selected ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              enabled[branch.key] === false && "line-through decoration-1",
            )}
          >
            {t(branch.label, branch.key)}
          </button>
        );
      })}
    </div>
  );
}

/** The open branch's name, its on/off switch (when it may be switched off) and its errors. */
export function BranchHeader({ state, branchKey }: { state: ReadyFlow; branchKey: string }) {
  const { model, draft, locked, errors, update } = state;
  const branch = model.branches[branchKey];
  if (!branch) return null;
  const path = `branches.${branchKey}.enabled`;
  const reason = model.editing === "lines" ? UPGRADE_LINES_ONLY : isLocked(locked, path) ? LOCKED_HINT : null;
  const problems = [...errorsFor(errors, `branches.${branchKey}`), ...errorsFor(errors, `order.${branchKey}`), ...errors.filter((error) => error.path === "branches" || error.path === "order")];
  const on = draft.branches[branchKey] !== false;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t(branch.label, branch.key)}</h3>
        <div className="flex items-center gap-2">
          {(isLocked(locked, path) || isLocked(locked, `order.${branchKey}`)) && <LockBadge />}
          {branch.toggleable && (
            <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
              {on ? "Offered" : "Not offered"}
              <Gate reason={reason}>
                <Toggle
                  checked={on}
                  label={`Offer ${t(branch.label, branch.key).toLowerCase()}`}
                  disabled={Boolean(reason)}
                  onChange={(value) => update(`branches.${branchKey}`, (current) => ({ ...current, branches: { ...current.branches, [branchKey]: value } }))}
                />
              </Gate>
            </span>
          )}
        </div>
      </div>
      <FieldErrors errors={problems} />
    </div>
  );
}
