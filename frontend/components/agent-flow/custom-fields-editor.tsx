"use client";

/** Up to 12 extra questions the agent asks (answers land on the record under `f_<key>`). */

import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { FlowFieldError } from "@/services/api";

import { FieldErrors, Gate, Toggle } from "./bits";
import { errorsFor } from "./rules";

export const MAX_CUSTOM_FIELDS = 12;
const MAX_CHOICES = 10;

const TYPES = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
  { value: "choice", label: "Choice" },
  { value: "bool", label: "Yes / no" },
];

/** `_new`: added in this session, so its key still follows the label (saved keys never change). */
export type CustomRow = { key: string; label: string; type: string; question: string; required: boolean; on: boolean; choices?: string[]; _new?: boolean };

function rowsFrom(value: unknown): CustomRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map((row) => ({
      key: String(row.key ?? ""),
      label: String(row.label ?? ""),
      type: String(row.type || "text"),
      question: String(row.question ?? ""),
      required: Boolean(row.required),
      on: row.on !== false,
      choices: Array.isArray(row.choices) ? row.choices.map(String) : undefined,
      _new: row._new === true,
    }));
}

/** "Shoe size" → "shoe_size" (2–19 chars, starts with a letter), unique among `taken`. */
function keyFor(label: string, taken: string[]): string {
  let base = label
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^[^a-z]+/, "")
    .replace(/_+$/, "")
    .slice(0, 16);
  if (base.length < 2) base = "field";
  let key = base;
  for (let n = 2; taken.includes(key); n += 1) key = `${base}_${n}`;
  return key;
}

export function CustomFieldsEditor({
  value,
  path,
  errors,
  disabled,
  reason,
  onChange,
}: {
  value: unknown;
  /** e.g. "steps.intake.options.custom" — row errors come as `<path>.<index>[.field]`. */
  path: string;
  errors: FlowFieldError[];
  disabled: boolean;
  reason?: string | null;
  onChange: (rows: CustomRow[]) => void;
}) {
  const rows = rowsFrom(value);
  const set = (index: number, patch: Partial<CustomRow>) =>
    onChange(
      rows.map((row, i) => {
        if (i !== index) return row;
        const next = { ...row, ...patch };
        if (row._new && patch.label !== undefined) next.key = keyFor(patch.label, rows.filter((_, j) => j !== i).map((other) => other.key));
        return next;
      }),
    );
  const add = () =>
    onChange([...rows, { key: keyFor("field", rows.map((row) => row.key)), label: "", type: "text", question: "", required: false, on: true, _new: true }]);

  return (
    <div className="space-y-3">
      {rows.length === 0 && <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">No custom questions.</p>}
      <ul className="space-y-2">
        {rows.map((row, index) => {
          const rowPath = `${path}.${index}`;
          return (
            <li key={index} className={cn("space-y-2 rounded-md border border-border p-3", !row.on && "bg-surface")}>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8.5rem]">
                <Input aria-label="Field name" placeholder="Field name, e.g. Shoe size" value={row.label} maxLength={60} disabled={disabled} onChange={(e) => set(index, { label: e.target.value })} />
                <Select aria-label="Answer type" value={row.type} disabled={disabled} onChange={(e) => set(index, { type: e.target.value })}>
                  {TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </Select>
              </div>
              <Input aria-label="Question" placeholder={`What is your ${row.label.trim().toLowerCase() || "answer"}?`} value={row.question} maxLength={200} disabled={disabled} onChange={(e) => set(index, { question: e.target.value })} />
              {row.type === "choice" && (
                <Input
                  aria-label="Choices, separated by commas"
                  placeholder="Choices: small, medium, large"
                  value={(row.choices ?? []).join(",")}
                  disabled={disabled}
                  onChange={(e) => set(index, { choices: e.target.value.split(",").slice(0, MAX_CHOICES) })}
                />
              )}
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <div className="flex flex-wrap items-center gap-4">
                  <span className="inline-flex items-center gap-2">
                    <Toggle checked={row.on} label={`Ask ${row.label || "this question"}`} disabled={disabled} onChange={(on) => set(index, { on })} />
                    <span className="text-muted-foreground" aria-hidden>
                      On
                    </span>
                  </span>
                  <label className="inline-flex items-center gap-2">
                    <input type="checkbox" className="h-4 w-4 accent-primary" checked={row.required} disabled={disabled} onChange={(e) => set(index, { required: e.target.checked })} />
                    <span className="text-muted-foreground">Required</span>
                  </label>
                  <code className="rounded bg-secondary px-1.5 py-0.5 text-[11.5px] text-muted-foreground" title="Saved on records as">
                    f_{row.key}
                  </code>
                </div>
                <Button type="button" variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" disabled={disabled} onClick={() => onChange(rows.filter((_, i) => i !== index))}>
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  Remove
                </Button>
              </div>
              <FieldErrors errors={errorsFor(errors, rowPath)} />
            </li>
          );
        })}
      </ul>
      <FieldErrors errors={errors.filter((error) => error.path === path)} />
      <Gate reason={reason}>
        <Button type="button" variant="outline" size="sm" onClick={add} disabled={disabled || rows.length >= MAX_CUSTOM_FIELDS}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add question
        </Button>
      </Gate>
      {rows.length >= MAX_CUSTOM_FIELDS && <span className="ml-2 text-xs text-muted-foreground">Up to {MAX_CUSTOM_FIELDS}.</span>}
    </div>
  );
}
