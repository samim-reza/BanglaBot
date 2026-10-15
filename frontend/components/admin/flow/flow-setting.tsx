"use client";

import { cn } from "@/lib/utils";

import { LockButton } from "./lock-button";

/**
 * One setting: label · control (what calls use) · the owner's own value · lock.
 * A locked setting edits its lock value (superadmin); an open one edits the owner's value.
 */
export function FlowSetting({
  label,
  hint,
  owner,
  locked,
  canLock,
  error,
  onToggleLock,
  children,
}: {
  label: string;
  hint?: string;
  /** The owner's own value as text; undefined = they never set it. */
  owner: string | undefined;
  locked: boolean;
  canLock: boolean;
  error?: string;
  onToggleLock: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-md px-2 py-2", locked && "bg-[#fffbeb] dark:bg-amber-500/5")}>
      <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5 sm:grid-cols-[minmax(8rem,1fr)_auto_9rem_auto]">
        <span className="min-w-0 text-[13.5px] font-medium" title={hint}>
          {label}
        </span>
        <span className="order-last col-span-2 sm:order-none sm:col-span-1">{children}</span>
        <span className="hidden truncate text-xs text-muted-foreground sm:block" title="The owner's own setting">
          Owner: {owner ?? "default"}
        </span>
        <LockButton locked={locked} canLock={canLock} onToggle={onToggleLock} label={label} />
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
