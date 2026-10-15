/** Label / value grids for the record page. */

import { cn } from "@/lib/utils";

/** Anything the agent stored (strings, numbers, flags, small objects) as readable text. */
export function looseValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map((item) => looseValue(item)).join(", ");
  return JSON.stringify(value);
}

export type KeyValueEntry = [label: string, value: string, wide?: boolean];

export function KeyValueList({ entries }: { entries: KeyValueEntry[] }) {
  return (
    <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
      {entries.map(([label, value, wide]) => (
        <div key={label} className={cn("min-w-0", wide && "sm:col-span-2")}>
          <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
          <dd className="mt-0.5 whitespace-pre-wrap break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
