"use client";

/**
 * Renders a vertical's field specs (records, catalog items, settings) as form
 * inputs. Values are a flat `{key: value}` map; `datetime` values are ISO
 * instants shown in the account's time zone.
 */

import { Field } from "@/components/page-header";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { WEEK_DAYS, fromZonedInput, t, toZonedInput } from "@/lib/vertical";
import type { CatalogItem, FieldSpec } from "@/services/api";

export type FormValues = Record<string, unknown>;

/** Defaults of every field, for a blank form. */
export function defaultValues(specs: FieldSpec[]): FormValues {
  const out: FormValues = {};
  for (const spec of specs) {
    if (spec.default !== null && spec.default !== undefined) out[spec.key] = spec.default;
  }
  return out;
}

/** Client-side required check; returns the first error message or null. */
export function validateValues(specs: FieldSpec[], values: FormValues): string | null {
  for (const spec of specs) {
    if (!spec.required) continue;
    const value = values[spec.key];
    const empty = value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
    if (empty) return `${t(spec.label)} is required`;
  }
  return null;
}

/** Drop empty strings so optional fields are not sent as "". */
export function compactValues(values: FormValues): FormValues {
  const out: FormValues = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === "" || value === undefined) continue;
    out[key] = value;
  }
  return out;
}

const DAY_NAMES: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };

function FieldInput({
  spec,
  value,
  onChange,
  catalog,
  timezone,
  disabled,
}: {
  spec: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  catalog?: CatalogItem[];
  timezone?: string;
  disabled?: boolean;
}) {
  const id = `field-${spec.key}`;
  const text = value === null || value === undefined ? "" : String(value);
  switch (spec.type) {
    case "textarea":
      return <Textarea id={id} rows={3} value={text} placeholder={spec.placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
    case "list":
      return (
        <Textarea
          id={id}
          rows={4}
          value={Array.isArray(value) ? value.join("\n") : text}
          placeholder={spec.placeholder || "One per line"}
          disabled={disabled}
          onChange={(e) =>
            onChange(
              e.target.value
                .split("\n")
                .map((line) => line.trimStart())
                .filter((line, index, all) => line || index === all.length - 1),
            )
          }
        />
      );
    case "money":
    case "number":
      return (
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          min={0}
          step={spec.type === "money" ? "0.01" : "1"}
          value={text}
          placeholder={spec.placeholder}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        />
      );
    case "phone":
      return <Input id={id} type="tel" value={text} placeholder={spec.placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
    case "date":
      return <Input id={id} type="date" value={text.slice(0, 10)} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
    case "time":
      return <Input id={id} type="time" value={text.slice(0, 5)} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
    case "datetime":
      return (
        <Input
          id={id}
          type="datetime-local"
          value={toZonedInput(text, timezone)}
          disabled={disabled}
          onChange={(e) => onChange(fromZonedInput(e.target.value, timezone))}
        />
      );
    case "bool":
      return (
        <span className="flex h-10 items-center gap-2">
          <input
            id={id}
            type="checkbox"
            className="h-4 w-4 accent-primary"
            checked={Boolean(value)}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span className="text-sm text-muted-foreground">{Boolean(value) ? "On" : "Off"}</span>
        </span>
      );
    case "select":
      return (
        <Select id={id} value={text} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {!spec.required && <option value="">—</option>}
          {spec.required && !text && <option value="">Choose…</option>}
          {spec.options.map((option) => (
            <option key={option.value} value={option.value}>
              {t(option.label)}
            </option>
          ))}
        </Select>
      );
    case "catalog":
      return (
        <Select id={id} value={text} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">{spec.required ? "Choose…" : "—"}</option>
          {(catalog ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
              {item.active ? "" : " (inactive)"}
            </option>
          ))}
        </Select>
      );
    case "days":
    case "multiselect": {
      const selected = Array.isArray(value) ? value.map(String) : [];
      const choices =
        spec.type === "days"
          ? WEEK_DAYS.map((day) => ({ value: day, label: DAY_NAMES[day] }))
          : spec.options.map((option) => ({ value: option.value, label: t(option.label) }));
      return (
        <div className="flex flex-wrap gap-1.5" role="group" aria-labelledby={`${id}-label`} id={id}>
          {choices.map((choice) => {
            const on = selected.includes(choice.value);
            return (
              <button
                key={choice.value}
                type="button"
                disabled={disabled}
                aria-pressed={on}
                onClick={() => onChange(on ? selected.filter((item) => item !== choice.value) : [...selected, choice.value])}
                className={cn(
                  "h-9 min-w-11 rounded-md border px-3 text-sm font-medium transition",
                  on ? "border-primary bg-primary text-primary-foreground" : "border-input bg-card text-foreground hover:bg-accent",
                )}
              >
                {choice.label}
              </button>
            );
          })}
        </div>
      );
    }
    default:
      return <Input id={id} value={text} placeholder={spec.placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
  }
}

export function SchemaFields({
  specs,
  values,
  onChange,
  catalog,
  timezone,
  disabled,
  className,
  wide = ["textarea", "list", "days", "multiselect"],
}: {
  specs: FieldSpec[];
  values: FormValues;
  onChange: (next: FormValues) => void;
  catalog?: CatalogItem[];
  timezone?: string;
  disabled?: boolean;
  className?: string;
  /** Field types that take a full row. */
  wide?: string[];
}) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2", className)}>
      {specs.map((spec) => {
        const label = `${t(spec.label)}${spec.required ? " *" : ""}`;
        const input = (
          <FieldInput
            spec={spec}
            value={values[spec.key]}
            catalog={catalog}
            timezone={timezone}
            disabled={disabled}
            onChange={(value) => onChange({ ...values, [spec.key]: value })}
          />
        );
        const span = wide.includes(spec.type) ? "sm:col-span-2" : undefined;
        if (spec.type === "days" || spec.type === "multiselect") {
          // A group of buttons must not sit inside a <label> (a click on the text would press the first one).
          const hint = t(spec.help);
          return (
            <div key={spec.key} className={cn("flex flex-col gap-1.5 text-sm", span)}>
              <span id={`field-${spec.key}-label`} className="text-[13.5px] font-semibold text-muted-foreground">
                {label}
              </span>
              {input}
              {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
            </div>
          );
        }
        return (
          <Field key={spec.key} label={label} hint={t(spec.help)} className={span}>
            {input}
          </Field>
        );
      })}
    </div>
  );
}
