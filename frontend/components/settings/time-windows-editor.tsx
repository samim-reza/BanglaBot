"use client";

import { Plus, Trash2 } from "lucide-react";

import { InfoTip } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const MAX_TIME_WINDOWS = 6;

export type TimeWindow = { key: string; start: string; end: string };

export function windowsFrom(raw: unknown): TimeWindow[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => ({ key: String(item.key ?? ""), start: String(item.start ?? "").slice(0, 5), end: String(item.end ?? "").slice(0, 5) }));
}

export function TimeWindowsEditor({ windows, onChange, teams }: { windows: TimeWindow[]; onChange: (next: TimeWindow[]) => void; teams: unknown }) {
  const update = (index: number, values: Partial<TimeWindow>) => onChange(windows.map((item, i) => (i === index ? { ...item, ...values } : item)));
  const add = () => {
    const last = windows[windows.length - 1];
    const start = last?.end || "09:00";
    const [hours, minutes] = start.split(":").map(Number);
    const endHours = Math.min(23, (hours || 0) + 3);
    const end = `${String(endHours).padStart(2, "0")}:${String(minutes || 0).padStart(2, "0")}`;
    onChange([...windows, { key: "", start, end: end > start ? end : "23:59" }]);
  };
  return (
    <fieldset className="space-y-3 sm:col-span-2">
      <legend className="flex items-center gap-1.5 text-[13.5px] font-semibold text-muted-foreground">
        Arrival windows
        <InfoTip label="About arrival windows">
          The time slots your agent offers on working days
          {typeof teams === "number" && teams > 0 ? `; each takes up to ${teams} booking${teams === 1 ? "" : "s"} (your teams per window)` : ""}. Name them the way
          callers would — morning, afternoon, evening.
        </InfoTip>
      </legend>
      {windows.length === 0 && <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">No arrival windows yet.</p>}
      <ul className="space-y-2">
        {windows.map((window, index) => (
          <li key={index} className="grid grid-cols-2 items-end gap-2 rounded-md border border-border p-2.5 sm:grid-cols-[1fr_8rem_8rem_auto] sm:border-0 sm:p-0">
            <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <label htmlFor={`window-key-${index}`} className={cn("text-xs font-medium text-muted-foreground", index > 0 && "sm:sr-only")}>
                Name
              </label>
              <Input
                id={`window-key-${index}`}
                value={window.key}
                maxLength={20}
                placeholder="morning"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => update(index, { key: e.target.value.toLowerCase().replace(/[^a-z_]/g, "") })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor={`window-start-${index}`} className={cn("text-xs font-medium text-muted-foreground", index > 0 && "sm:sr-only")}>
                From
              </label>
              <Input id={`window-start-${index}`} type="time" value={window.start} onChange={(e) => update(index, { start: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor={`window-end-${index}`} className={cn("text-xs font-medium text-muted-foreground", index > 0 && "sm:sr-only")}>
                Until
              </label>
              <Input id={`window-end-${index}`} type="time" value={window.end} onChange={(e) => update(index, { end: e.target.value })} />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="col-span-2 w-full text-muted-foreground hover:text-destructive sm:col-span-1 sm:w-10"
              aria-label={`Remove arrival window ${window.key || index + 1}`}
              onClick={() => onChange(windows.filter((_, i) => i !== index))}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              <span className="sm:hidden">Remove</span>
            </Button>
          </li>
        ))}
      </ul>
      <Button type="button" variant="outline" size="sm" onClick={add} disabled={windows.length >= MAX_TIME_WINDOWS}>
        <Plus className="h-3.5 w-3.5" aria-hidden />
        Add window
      </Button>
      {windows.length >= MAX_TIME_WINDOWS && <span className="ml-2 text-xs text-muted-foreground">Up to {MAX_TIME_WINDOWS} windows.</span>}
    </fieldset>
  );
}
