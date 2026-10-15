"use client";

import { MiniSwitch } from "@/components/admin/form-bits";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** A compact number input for table cells; empty → 0. */
export function NumCell({ value, onChange, label, disabled, step, className, error }: { value: number; onChange: (n: number) => void; label: string; disabled?: boolean; step?: string; className?: string; error?: string }) {
  return (
    <Input
      type="number"
      min={0}
      step={step ?? "1"}
      aria-label={label}
      aria-invalid={error ? true : undefined}
      title={error}
      className={cn("h-8 w-20 px-2 text-right text-[13px] tabular-nums", error && "border-destructive", className)}
      value={Number.isFinite(value) ? String(value) : ""}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
    />
  );
}

export function TextCell({ value, onChange, label, disabled, className, mono, placeholder, error }: { value: string; onChange: (v: string) => void; label: string; disabled?: boolean; className?: string; mono?: boolean; placeholder?: string; error?: string }) {
  return (
    <Input
      aria-label={label}
      aria-invalid={error ? true : undefined}
      title={error}
      className={cn("h-8 px-2 text-[13px]", mono && "font-mono", error && "border-destructive", className)}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function SwitchCell({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return <MiniSwitch checked={checked} onChange={onChange} label={label} disabled={disabled} />;
}

/** A labelled control in a details grid. */
export function Labeled({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-xs font-semibold text-muted-foreground" title={hint}>
        {label}
      </span>
      {children}
    </label>
  );
}

/** Pick any of `options` as toggle chips; `emptyLabel` names what none selected means. */
export function ChipSelect({
  options,
  value,
  onChange,
  label,
  disabled,
  emptyLabel,
}: {
  options: { key: string; label: string }[];
  value: string[];
  onChange: (next: string[]) => void;
  label: string;
  disabled?: boolean;
  emptyLabel?: string;
}) {
  const toggle = (key: string) => onChange(value.includes(key) ? value.filter((item) => item !== key) : [...value, key]);
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      {options.map((option) => {
        const on = value.includes(option.key);
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={on}
            disabled={disabled}
            onClick={() => toggle(option.key)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[12.5px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
              on ? "border-primary bg-accent text-accent-foreground" : "border-border text-muted-foreground hover:bg-secondary",
            )}
          >
            {option.label}
          </button>
        );
      })}
      {emptyLabel && value.length === 0 && <span className="text-xs text-muted-foreground">{emptyLabel}</span>}
    </div>
  );
}

export const humanKey = (key: string) => key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
