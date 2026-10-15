"use client";

import { Lock, LockOpen } from "lucide-react";

import { cn } from "@/lib/utils";

/** Lock / unlock one setting. Without permission a lock still shows, read-only. */
export function LockButton({ locked, canLock, onToggle, label }: { locked: boolean; canLock: boolean; onToggle: () => void; label: string }) {
  if (!canLock) {
    return locked ? (
      <span className="inline-flex h-7 w-7 items-center justify-center text-[#92400e] dark:text-amber-300" title="Locked — the owner can't change it">
        <Lock className="h-3.5 w-3.5" aria-label={`${label}: locked`} />
      </span>
    ) : (
      <span className="inline-block h-7 w-7" aria-hidden="true" />
    );
  }
  return (
    <button
      type="button"
      aria-pressed={locked}
      aria-label={locked ? `Unlock ${label}` : `Lock ${label}`}
      title={locked ? "Locked — click to let the owner change it" : "Lock at this value — the owner can't change it"}
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      className={cn(
        "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        locked
          ? "bg-[#fef3c7] text-[#92400e] hover:bg-[#fde68a] dark:bg-amber-500/15 dark:text-amber-300"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground",
      )}
    >
      {locked ? <Lock className="h-3.5 w-3.5" /> : <LockOpen className="h-3.5 w-3.5" />}
    </button>
  );
}
