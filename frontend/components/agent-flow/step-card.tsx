"use client";

/** One step of the flow: label, one-line description, on/off, ↑/↓ and a way into its drawer. */

import { ArrowDown, ArrowUp, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { FlowSkill } from "@/services/api";

import { Gate, LockBadge, Toggle } from "./bits";

export type StepMove = {
  /** The step sits in a group the owner may reorder. */
  movable: boolean;
  up: (() => void) | null;
  down: (() => void) | null;
  /** Why moving is off (plan, lock); null = allowed where the rules permit. */
  reason: string | null;
};

const moveButton =
  "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-35";

export function StepCard({
  skill,
  number,
  enabled,
  edited,
  locked,
  errorCount,
  toggleReason,
  move,
  onToggle,
  onOpen,
}: {
  skill: FlowSkill;
  number?: number;
  enabled: boolean;
  edited: boolean;
  locked: boolean;
  errorCount: number;
  /** Why the switch is off-limits; null = usable. */
  toggleReason: string | null;
  move?: StepMove;
  onToggle: (value: boolean) => void;
  onOpen: () => void;
}) {
  const label = t(skill.label, skill.key);
  const description = t(skill.description);
  const openable = skill.lines.length > 0 || skill.options.length > 0;
  return (
    <li
      className={cn(
        "rounded-lg border bg-card transition-colors",
        errorCount ? "border-destructive/60" : "border-border",
        !enabled && "bg-surface",
      )}
    >
      <div className="flex items-center gap-3 p-3">
        {number !== undefined && (
          <span
            aria-hidden
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
          onClick={onOpen}
          disabled={!openable}
          className="min-w-0 flex-1 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default"
          aria-label={openable ? `Edit ${label}` : label}
        >
          <span className="flex flex-wrap items-center gap-1.5">
            <span className={cn("text-sm font-semibold", !enabled && "text-muted-foreground")}>{label}</span>
            {!enabled && <span className="rounded-full bg-secondary px-1.5 py-px text-[10.5px] font-semibold text-muted-foreground">Off</span>}
            {edited && <span className="rounded-full bg-accent px-1.5 py-px text-[10.5px] font-semibold text-accent-foreground">Edited</span>}
            {errorCount > 0 && <span className="text-[11.5px] font-semibold text-destructive">{errorCount === 1 ? "1 to fix" : `${errorCount} to fix`}</span>}
          </span>
          {description && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{description}</span>}
        </button>
        {locked && <LockBadge />}
        <div className="flex shrink-0 items-center gap-1">
          {move?.movable && (
            <Gate reason={move.reason}>
              <span className="inline-flex">
                <button type="button" className={moveButton} aria-label={`Move ${label} up`} disabled={!move.up} onClick={() => move.up?.()}>
                  <ArrowUp className="h-3.5 w-3.5" aria-hidden />
                </button>
                <button type="button" className={moveButton} aria-label={`Move ${label} down`} disabled={!move.down} onClick={() => move.down?.()}>
                  <ArrowDown className="h-3.5 w-3.5" aria-hidden />
                </button>
              </span>
            </Gate>
          )}
          {skill.toggleable && (
            <Gate reason={toggleReason}>
              <Toggle checked={enabled} onChange={onToggle} label={`${label} on`} disabled={Boolean(toggleReason)} />
            </Gate>
          )}
          {openable && (
            <button type="button" onClick={onOpen} className={moveButton} aria-label={`Open ${label}`} tabIndex={-1}>
              <ChevronRight className="h-4 w-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </li>
  );
}
