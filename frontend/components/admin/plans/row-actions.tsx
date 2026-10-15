"use client";

import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";

const ICON_BTN =
  "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-35";

/** ↑ / ↓ to reorder a catalog row. */
export function MoveButtons({ name, first, last, disabled, onMove }: { name: string; first: boolean; last: boolean; disabled?: boolean; onMove: (step: -1 | 1) => void }) {
  return (
    <span className="inline-flex">
      <button type="button" className={ICON_BTN} aria-label={`Move ${name} up`} disabled={disabled || first} onClick={() => onMove(-1)}>
        <ArrowUp className="h-3.5 w-3.5" />
      </button>
      <button type="button" className={ICON_BTN} aria-label={`Move ${name} down`} disabled={disabled || last} onClick={() => onMove(1)}>
        <ArrowDown className="h-3.5 w-3.5" />
      </button>
    </span>
  );
}

/** Open the row's details, or remove it (keys still in use are refused by the API: hide them). */
export function RowTools({ name, open, onToggle, onRemove, disabled }: { name: string; open: boolean; onToggle: () => void; onRemove: () => void; disabled?: boolean }) {
  return (
    <span className="inline-flex">
      <button type="button" className={ICON_BTN} aria-expanded={open} aria-label={open ? `Hide ${name} details` : `Edit ${name} details`} onClick={onToggle}>
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>
      <button
        type="button"
        className={cn(ICON_BTN, "hover:text-destructive")}
        aria-label={`Remove ${name}`}
        title="Remove (a key still in use can only be hidden)"
        disabled={disabled}
        onClick={onRemove}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </span>
  );
}
