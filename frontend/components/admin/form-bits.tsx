"use client";

import { cn } from "@/lib/utils";

/** Accessible attributes tying an input to its hint / error line in `FormField`. */
export function fieldProps(id: string, error?: string | null, hint?: React.ReactNode) {
  return {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : hint ? `${id}-hint` : undefined,
  } as const;
}

/** Label + control + hint or error. Pair the control with `fieldProps(id, error, hint)`. */
export function FormField({
  id,
  label,
  required,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  hint?: React.ReactNode;
  error?: string | null;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-[13.5px] font-semibold text-muted-foreground">
        {label}
        {required && (
          <>
            <span className="text-destructive" aria-hidden="true">
              {" "}
              *
            </span>
            <span className="sr-only"> (required)</span>
          </>
        )}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FormSection({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <fieldset className="min-w-0 space-y-3">
      <legend className="mb-1">
        <span className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</span>
        {description && <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>}
      </legend>
      {children}
    </fieldset>
  );
}

/** On/off switch (role="switch"), with its label and optional description beside it. */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-4 rounded-md border border-border p-3 text-left text-sm transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
    >
      <span className="min-w-0">
        <span className="block font-medium">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>}
      </span>
      <span
        aria-hidden="true"
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors",
          checked ? "bg-primary" : "bg-border",
        )}
      >
        <span
          className={cn(
            "inline-block h-5 w-5 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-[22px]" : "translate-x-0.5",
          )}
        />
      </span>
    </button>
  );
}

/** After a failed submit, move focus to the first field marked invalid in the form. */
export function focusFirstInvalid(formId: string) {
  window.requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(`#${formId} [aria-invalid="true"]`)?.focus();
  });
}

// ------------------------------------------------------------------ validation (mirrors backend/app/schemas)

export const USERNAME_RE = /^[A-Za-z0-9_.-]+$/;

export function digitCount(value: string): number {
  return value.replace(/\D/g, "").length;
}

/** Optional phone: empty, or at least 7 digits (the API's rule). */
export function phoneError(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  return digitCount(text) < 7 ? "Doesn't look like a phone number." : null;
}

export function emailError(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text) ? null : "Enter a valid email address.";
}

export function timezoneError(value: string): string | null {
  const text = value.trim();
  if (!text) return "Time zone is required.";
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: text });
    return null;
  } catch {
    return "Unknown time zone — use an IANA name such as America/New_York.";
  }
}

export function currencyError(value: string): string | null {
  return /^[A-Za-z]{3}$/.test(value.trim()) ? null : "Use a 3-letter currency code, e.g. USD.";
}

export function emergencyError(value: string): string | null {
  const digits = digitCount(value);
  return digits >= 2 && digits <= 8 ? null : "Use a short number such as 911, 999 or 112.";
}
