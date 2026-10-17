"use client";

/** Settings → Closures: holidays and days off the agent never books (whole business or one person). */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CalendarOff, LoaderCircle, Plus, Trash2 } from "lucide-react";

import { SectionCard } from "@/components/portal/kit";
import { FormRow, useSaver } from "@/components/settings/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { closuresApi, formatApiError, type Closure, type ClosureInput, type ClosuresView } from "@/services/api";

const MAX_LABEL = 60;
/** Rows shown before "Show all". */
const FIRST = 8;
const EMPTY = { start: "", end: "", label: "", item: "" };

/** "Thu, Nov 26" — a YYYY-MM-DD read as a calendar day (no time-zone shift). */
function dayLabel(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(year, (month || 1) - 1, day || 1);
  return new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" }).format(date);
}

function spanLabel(closure: Closure): string {
  return closure.end && closure.end !== closure.start ? `${dayLabel(closure.start)} – ${dayLabel(closure.end)}` : dayLabel(closure.start);
}

const asInput = ({ start, end, label, item_id }: Closure): ClosureInput => ({ start, end, label, item_id });

export function ClosuresSection() {
  const [view, setView] = useState<ClosuresView | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [all, setAll] = useState(false);
  const { saving, error, setError, run } = useSaver();

  const load = useCallback(async () => {
    try {
      setView(await closuresApi.list());
      setLoadError(null);
    } catch (err) {
      setLoadError(formatApiError(err, "Could not load closures."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = (next: ClosureInput[], success: string) =>
    run(async () => {
      setView(await closuresApi.save(next));
    }, success);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (!view) return;
    if (!form.start) return setError("Pick a date.");
    if (form.end && form.end < form.start) return setError("The end date is before the start date.");
    const entry: ClosureInput = { start: form.start, end: form.end || form.start, label: form.label.trim(), item_id: form.item };
    if (await save([...view.closures.map(asInput), entry], "Closure added.")) setForm(EMPTY);
  };

  const remove = (index: number) => {
    if (!view) return;
    void save(view.closures.filter((_, i) => i !== index).map(asInput), "Closure removed.");
  };

  const items = view?.items ?? [];
  const nameOf = (id: string) => items.find((item) => item.id === id)?.name ?? "";
  const rows = view ? (all ? view.closures : view.closures.slice(0, FIRST)) : [];

  return (
    <SectionCard id="closures" icon={CalendarOff} title="Closures" description="Days your agent won't book.">
      {loadError ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <p role="alert" className="text-destructive">{loadError}</p>
          <Button type="button" size="sm" variant="outline" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : !view ? (
        <div className="h-24 animate-pulse rounded-md bg-secondary" role="status" aria-label="Loading" />
      ) : (
        <div className="space-y-5">
          {view.closures.length === 0 ? (
            <p className="text-sm text-muted-foreground">No closures.</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {rows.map((closure, index) => (
                <li key={`${closure.start}-${closure.end}-${closure.item_id}-${index}`} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                  <span className="w-40 shrink-0 font-medium tabular-nums">{spanLabel(closure)}</span>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">
                    {[closure.label, closure.item_id ? nameOf(closure.item_id) : ""].filter(Boolean).join(" · ") || "Closed"}
                  </span>
                  <Button type="button" size="sm" variant="ghost" disabled={saving} onClick={() => remove(index)} aria-label={`Remove ${spanLabel(closure)}`}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {view.closures.length > FIRST && (
            <Button type="button" size="sm" variant="ghost" onClick={() => setAll(!all)}>
              {all ? "Show fewer" : `Show all (${view.closures.length})`}
            </Button>
          )}

          <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto] lg:items-end" onSubmit={add} noValidate>
            <FormRow id="closure-start" label="From">
              <Input id="closure-start" type="date" min={view.today} value={form.start} disabled={saving} onChange={(e) => setForm({ ...form, start: e.target.value })} />
            </FormRow>
            <FormRow id="closure-end" label="To">
              <Input id="closure-end" type="date" min={form.start || view.today} value={form.end} disabled={saving} onChange={(e) => setForm({ ...form, end: e.target.value })} />
            </FormRow>
            <FormRow id="closure-label" label="Label">
              <Input id="closure-label" maxLength={MAX_LABEL} placeholder="Thanksgiving" value={form.label} disabled={saving} onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </FormRow>
            {items.length > 0 ? (
              <FormRow id="closure-item" label="Who">
                <Select id="closure-item" value={form.item} disabled={saving} onChange={(e) => setForm({ ...form, item: e.target.value })}>
                  <option value="">Whole business</option>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </FormRow>
            ) : (
              <span className="hidden lg:block" aria-hidden />
            )}
            <Button type="submit" disabled={saving || !form.start}>
              {saving ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
              Add
            </Button>
          </form>
          {error && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
        </div>
      )}
    </SectionCard>
  );
}
