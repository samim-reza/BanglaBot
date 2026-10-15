"use client";

/** Building blocks shared by the settings cards (saving state, dirty registry, rows, save bar). */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { LoaderCircle, RotateCcw } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { InfoTip } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatApiError } from "@/services/api";

/** Saving state + inline error for one card. */
export function useSaver() {
  const toast = useAppToast();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (task: () => Promise<void>, success: string, fallback = "Could not save your changes.") => {
      setSaving(true);
      setError(null);
      try {
        await task();
        toast.success(success);
        return true;
      } catch (err) {
        setError(formatApiError(err, fallback));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [toast],
  );
  return { saving, error, setError, run };
}

export function validTimeZone(zone: string): boolean {
  if (!zone.trim()) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone.trim() });
    return true;
  } catch {
    return false;
  }
}

/** Page-level registry of which cards have unsaved edits (for the tab dots and the unload guard). */
export const DirtyContext = createContext<(id: string, dirty: boolean) => void>(() => undefined);

export function useReportDirty(id: string, dirty: boolean) {
  const report = useContext(DirtyContext);
  useEffect(() => {
    report(id, dirty);
  }, [id, dirty, report]);
  useEffect(() => () => report(id, false), [id, report]);
}

export function FormRow({
  id,
  label,
  hint,
  info,
  aside,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: React.ReactNode;
  /** Longer explanation behind an info icon. */
  info?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 text-sm", className)}>
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-1.5">
          <label htmlFor={id} className="text-[13.5px] font-semibold text-muted-foreground">
            {label}
          </label>
          {info && <InfoTip label={`About ${label.toLowerCase()}`}>{info}</InfoTip>}
        </span>
        {aside}
      </div>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-xs leading-relaxed text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

export function Counter({ value, max, warnAt }: { value: number; max: number; warnAt?: number }) {
  const over = value > max;
  const warn = warnAt !== undefined && value > warnAt;
  return (
    <span
      className={cn(
        "shrink-0 text-xs tabular-nums",
        over ? "font-semibold text-destructive" : warn ? "font-medium text-amber-700 dark:text-amber-300" : "text-muted-foreground",
      )}
      aria-live="polite"
    >
      {value.toLocaleString("en-US")} / {max.toLocaleString("en-US")}
    </span>
  );
}

export function Segmented<T extends string>({
  name,
  label,
  value,
  options,
  onChange,
}: {
  name: string;
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-1.5 text-sm">
      <legend className="mb-1.5 text-[13.5px] font-semibold text-muted-foreground">{label}</legend>
      <div className="inline-flex w-full rounded-md border border-input bg-card p-0.5 sm:w-auto">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex h-9 flex-1 cursor-pointer items-center justify-center rounded px-4 text-sm font-medium transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring sm:flex-none",
                active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <input
                type="radio"
                className="sr-only"
                name={name}
                value={option.value}
                checked={active}
                onChange={() => onChange(option.value)}
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function SaveBar({
  dirty,
  saving,
  error,
  onReset,
  label = "Save",
}: {
  dirty: boolean;
  saving: boolean;
  error: string | null;
  onReset: () => void;
  label?: string;
}) {
  return (
    <div className="mt-5 space-y-3 border-t border-border pt-4">
      {error && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {saving ? (
            "Saving…"
          ) : dirty ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-300">
              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
              Unsaved changes
            </span>
          ) : null}
        </p>
        <div className="flex gap-2">
          {dirty && (
            <Button type="button" variant="ghost" size="sm" onClick={onReset} disabled={saving}>
              <RotateCcw className="h-3.5 w-3.5" aria-hidden />
              Discard
            </Button>
          )}
          <Button type="submit" size="sm" disabled={!dirty || saving} className="flex-1 sm:flex-none">
            {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            {label}
          </Button>
        </div>
      </div>
    </div>
  );
}
