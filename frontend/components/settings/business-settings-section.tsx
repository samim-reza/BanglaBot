"use client";

import { FormEvent, useMemo } from "react";
import { SlidersHorizontal } from "lucide-react";

import { SectionCard, useDraft } from "@/components/portal/kit";
import { SchemaFields, compactValues, type FormValues } from "@/components/schema-form";
import { SaveBar, useReportDirty, useSaver } from "@/components/settings/shared";
import { TimeWindowsEditor, windowsFrom, type TimeWindow } from "@/components/settings/time-windows-editor";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { merchantApi, type FieldSpec, type VerticalSpec } from "@/services/api";

type ConfigForm = { values: FormValues; windows: TimeWindow[] };

function configFrom(specs: FieldSpec[], config: Record<string, unknown>, hasWindows: boolean): ConfigForm {
  const values: FormValues = {};
  for (const spec of specs) {
    const value = config[spec.key];
    if (value !== undefined && value !== null) values[spec.key] = value;
  }
  return { values, windows: hasWindows ? windowsFrom(config.time_windows) : [] };
}

/** What the backend's `Vertical.config()` returns: the stored settings over the defaults. */
function mergedConfig(vertical: VerticalSpec, stored: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...vertical.config_defaults };
  for (const [key, value] of Object.entries(stored ?? {})) {
    if (value !== null && value !== undefined) merged[key] = value;
  }
  return merged;
}

function validateConfig(specs: FieldSpec[], form: ConfigForm, hasWindows: boolean): string | null {
  for (const spec of specs) {
    const value = form.values[spec.key];
    if ((spec.type === "number" || spec.type === "money") && typeof value === "number" && value < 0) {
      return `${t(spec.label)} can't be negative.`;
    }
  }
  if (!hasWindows) return null;
  if (!form.windows.length) return "Add at least one arrival window.";
  const keys = new Set<string>();
  for (const [index, window] of form.windows.entries()) {
    const label = `Arrival window ${index + 1}`;
    if (!/^[a-z_]{1,20}$/.test(window.key)) return `${label}: give it a short name in lowercase letters, e.g. morning.`;
    if (keys.has(window.key)) return `${label}: the name "${window.key}" is used twice.`;
    keys.add(window.key);
    if (!window.start || !window.end) return `${label}: set a start and an end time.`;
    if (window.end <= window.start) return `${label}: the end time must be after the start time.`;
  }
  return null;
}

function hasBusinessSettings(vertical: VerticalSpec): boolean {
  return vertical.config_fields.length > 0 || "time_windows" in (vertical.config_defaults ?? {});
}

export function BusinessSettingsSection({ onSaved }: { onSaved?: () => void }) {
  const { merchant, vertical, config, refresh } = useWorkspace();
  const specs = vertical.config_fields;
  const hasWindows = "time_windows" in (vertical.config_defaults ?? {});
  const source = useMemo(() => configFrom(specs, config, hasWindows), [specs, config, hasWindows]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("business", dirty);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const problem = validateConfig(specs, draft, hasWindows);
    if (problem) {
      setError(problem);
      return;
    }
    // Lists: drop the blank line the editor keeps while typing.
    const values: FormValues = {};
    for (const [key, value] of Object.entries(draft.values)) {
      values[key] = Array.isArray(value) ? value.map((item) => (typeof item === "string" ? item.trim() : item)).filter((item) => item !== "") : value;
    }
    const payload: Record<string, unknown> = compactValues(values);
    // A cleared field goes back to the default: the API drops keys sent as null.
    for (const spec of specs) {
      if (!(spec.key in payload) && source.values[spec.key] !== undefined) payload[spec.key] = null;
    }
    if (hasWindows) payload.time_windows = draft.windows.map(({ key, start, end }) => ({ key, start, end }));
    void run(async () => {
      const updated = await merchantApi.updateMe({ vertical_config: payload });
      commit(configFrom(specs, mergedConfig(vertical, updated.vertical_config ?? {}), hasWindows));
      await refresh();
      onSaved?.();
    }, vertical.scheduled ? "Booking rules saved." : "Business settings saved.");
  };

  if (!hasBusinessSettings(vertical)) return null;

  return (
    <SectionCard
      id="business"
      icon={SlidersHorizontal}
      title={vertical.scheduled ? "Booking rules" : "Business settings"}
      description="Empty fields use the default."
    >
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <SchemaFields
          specs={specs}
          values={draft.values}
          timezone={merchant.timezone}
          disabled={saving}
          onChange={(values) => setDraft((current) => ({ ...current, values }))}
        />
        {hasWindows && (
          <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
            <TimeWindowsEditor windows={draft.windows} teams={draft.values.teams} onChange={(windows) => setDraft((current) => ({ ...current, windows }))} />
          </div>
        )}
        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} />
      </form>
    </SectionCard>
  );
}
