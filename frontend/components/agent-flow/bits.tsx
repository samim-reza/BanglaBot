"use client";

/** Small controls shared by the call-flow editor. */

import { Lock } from "lucide-react";

import { HoverInfo } from "@/components/ui/hover-info";
import { cn } from "@/lib/utils";
import type { FlowFieldError } from "@/services/api";

import { LOCKED_HINT } from "./rules";

/** An on/off switch (a real button with role="switch"). */
export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (value: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!checked);
      }}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-primary" : "bg-input",
      )}
    >
      <span className={cn("inline-block h-4 w-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  );
}

/** Wraps a (possibly disabled) control so hovering it explains why it can't be used. */
export function Gate({ reason, children }: { reason?: string | null; children: React.ReactNode }) {
  if (!reason) return <>{children}</>;
  return (
    <HoverInfo width={240} trigger={<span className="inline-flex">{children}</span>}>
      <span className="block text-xs leading-relaxed text-muted-foreground">{reason}</span>
    </HoverInfo>
  );
}

export function LockBadge({ hint = LOCKED_HINT }: { hint?: string }) {
  return (
    <HoverInfo
      width={240}
      trigger={
        <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11.5px] font-semibold text-muted-foreground" tabIndex={0} aria-label={`Locked: ${hint}`}>
          <Lock className="h-3 w-3" aria-hidden />
          Locked
        </span>
      }
    >
      <span className="block text-xs leading-relaxed text-muted-foreground">{hint}</span>
    </HoverInfo>
  );
}

/** Server messages for one field. */
export function FieldErrors({ errors, id }: { errors: FlowFieldError[]; id?: string }) {
  if (!errors.length) return null;
  return (
    <ul id={id} role="alert" className="space-y-0.5 text-xs font-medium text-destructive">
      {errors.map((error) => (
        <li key={`${error.path}:${error.message}`}>{error.message}</li>
      ))}
    </ul>
  );
}

/** Segmented choice (direction, language). */
export function Segments<T extends string>({ label, value, options, onChange, size = "md" }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void; size?: "sm" | "md" }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-input bg-card p-0.5">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3.5 text-sm",
              active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
