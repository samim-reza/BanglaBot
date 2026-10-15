"use client";

/** Built-in details the agent collects: On / Required / Ask, and an optional reworded question. */

import { InfoTip } from "@/components/portal/kit";
import { Input } from "@/components/ui/input";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { Label } from "@/services/api";

import { Toggle } from "./bits";

export type IntakeRow = { key: string; on: boolean; required: boolean; ask: boolean; question?: string; label?: string | Partial<Label> };

function rowsFrom(value: unknown): IntakeRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && typeof (row as { key?: unknown }).key === "string")
    .map((row) => ({
      key: String(row.key),
      on: Boolean(row.on),
      required: Boolean(row.required),
      ask: row.ask !== false,
      question: typeof row.question === "string" ? row.question : undefined,
      label: (row.label as IntakeRow["label"]) ?? undefined,
    }));
}

/** The default rows (every built-in field, in order) with the draft's settings on top. */
export function intakeRows(value: unknown, defaults: unknown): IntakeRow[] {
  const current = new Map(rowsFrom(value).map((row) => [row.key, row]));
  const base = rowsFrom(defaults);
  return (base.length ? base : [...current.values()]).map((row) => ({ ...row, ...current.get(row.key), label: row.label ?? current.get(row.key)?.label }));
}

function labelOf(row: IntakeRow): string {
  if (typeof row.label === "string" && row.label) return row.label;
  if (row.label && typeof row.label === "object") return t(row.label, humanize(row.key));
  return humanize(row.key);
}

const check = "h-4 w-4 accent-primary disabled:cursor-not-allowed disabled:opacity-50";

export function IntakeFieldsTable({ value, defaults, disabled, onChange }: { value: unknown; defaults: unknown; disabled: boolean; onChange: (rows: IntakeRow[]) => void }) {
  const rows = intakeRows(value, defaults);
  const set = (key: string, patch: Partial<IntakeRow>) => onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  if (!rows.length) return <p className="text-sm text-muted-foreground">No built-in fields.</p>;
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-[34rem] text-sm">
        <thead className="bg-surface text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-semibold">Field</th>
            <th className="px-2 py-2 text-center font-semibold">On</th>
            <th className="px-2 py-2 text-center font-semibold">
              <span className="inline-flex items-center gap-1">
                Required
                <InfoTip label="About required">Asked until the caller gives it.</InfoTip>
              </span>
            </th>
            <th className="px-2 py-2 text-center font-semibold">
              <span className="inline-flex items-center gap-1">
                Ask
                <InfoTip label="About ask">Off = saved only if the caller mentions it.</InfoTip>
              </span>
            </th>
            <th className="px-3 py-2 text-left font-semibold">Question</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => {
            const label = labelOf(row);
            const off = disabled || !row.on;
            return (
              <tr key={row.key} className={cn(!row.on && "text-muted-foreground")}>
                <td className="px-3 py-2 font-medium">{label}</td>
                <td className="px-2 py-2 text-center">
                  <span className="inline-flex">
                    <Toggle checked={row.on} label={`Collect ${label}`} disabled={disabled} onChange={(on) => set(row.key, { on })} />
                  </span>
                </td>
                <td className="px-2 py-2 text-center">
                  <input type="checkbox" className={check} aria-label={`${label} required`} checked={row.required} disabled={off} onChange={(e) => set(row.key, { required: e.target.checked })} />
                </td>
                <td className="px-2 py-2 text-center">
                  <input
                    type="checkbox"
                    className={check}
                    aria-label={`Ask for ${label}`}
                    checked={row.required || row.ask}
                    disabled={off || row.required}
                    onChange={(e) => set(row.key, { ask: e.target.checked })}
                  />
                </td>
                <td className="px-3 py-2">
                  <Input
                    className="h-8"
                    aria-label={`Question for ${label}`}
                    value={row.question ?? ""}
                    maxLength={200}
                    placeholder="Default question"
                    disabled={off}
                    onChange={(e) => set(row.key, { question: e.target.value })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
