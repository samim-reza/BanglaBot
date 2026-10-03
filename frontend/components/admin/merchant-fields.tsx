"use client";

import { useMemo } from "react";
import { Lock } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { AdminMeta, Language, VerticalKey, VerticalSpec, VoicePersona } from "@/services/api";

import { FormField, fieldProps } from "./form-bits";
import { planOf, planPrice, regionOf } from "./use-admin-meta";

export type LocaleValues = { region: string; timezone: string; currency: string; emergency_number: string };
export type LocaleErrors = Partial<Record<keyof LocaleValues, string | null>>;

/** The region's preset values for the three editable locale fields. */
export function regionPreset(meta: AdminMeta | null, code: string): Omit<LocaleValues, "region"> | null {
  const region = regionOf(meta, code);
  return region ? { timezone: region.timezone, currency: region.currency, emergency_number: region.emergency } : null;
}

function useTimeZones(): string[] {
  return useMemo(() => {
    try {
      const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
      return intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
    } catch {
      return [];
    }
  }, []);
}

/**
 * Region preset + the account's time zone, currency and emergency number.
 * Picking a region refills the three fields; they stay editable afterwards.
 */
export function RegionFields({
  idPrefix,
  meta,
  value,
  errors = {},
  onChange,
  regionHint,
}: {
  idPrefix: string;
  meta: AdminMeta | null;
  value: LocaleValues;
  errors?: LocaleErrors;
  onChange: (patch: Partial<LocaleValues>) => void;
  regionHint?: string;
}) {
  const zones = useTimeZones();
  const listId = `${idPrefix}-zones`;
  const hint = regionHint ?? "Fills in the time zone, currency and emergency number below. You can still edit them.";
  return (
    <>
      <FormField id={`${idPrefix}-region`} label="Region" hint={hint} error={errors.region}>
        <Select
          {...fieldProps(`${idPrefix}-region`, errors.region, hint)}
          value={value.region}
          disabled={!meta}
          onChange={(event) => {
            const code = event.target.value;
            onChange({ region: code, ...(regionPreset(meta, code) ?? {}) });
          }}
        >
          {!meta && <option value={value.region}>{value.region || "Loading…"}</option>}
          {meta?.regions.map((region) => (
            <option key={region.code} value={region.code}>
              {region.label} ({region.code})
            </option>
          ))}
        </Select>
      </FormField>
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField id={`${idPrefix}-timezone`} label="Time zone" error={errors.timezone} className="sm:col-span-3">
          <Input
            {...fieldProps(`${idPrefix}-timezone`, errors.timezone)}
            value={value.timezone}
            onChange={(event) => onChange({ timezone: event.target.value })}
            list={zones.length ? listId : undefined}
            autoComplete="off"
            spellCheck={false}
            placeholder="America/New_York"
          />
          {zones.length > 0 && (
            <datalist id={listId}>
              {zones.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          )}
        </FormField>
        <FormField id={`${idPrefix}-currency`} label="Currency" error={errors.currency}>
          <Input
            {...fieldProps(`${idPrefix}-currency`, errors.currency)}
            value={value.currency}
            onChange={(event) => onChange({ currency: event.target.value.toUpperCase() })}
            maxLength={3}
            autoComplete="off"
            spellCheck={false}
            placeholder="USD"
            className="uppercase"
          />
        </FormField>
        <FormField id={`${idPrefix}-emergency`} label="Emergency number" error={errors.emergency_number} className="sm:col-span-2">
          <Input
            {...fieldProps(`${idPrefix}-emergency`, errors.emergency_number)}
            value={value.emergency_number}
            onChange={(event) => onChange({ emergency_number: event.target.value })}
            inputMode="tel"
            maxLength={16}
            autoComplete="off"
            placeholder="911"
          />
        </FormField>
      </div>
    </>
  );
}

export function PlanField({
  id,
  meta,
  value,
  onChange,
  error,
}: {
  id: string;
  meta: AdminMeta | null;
  value: string;
  onChange: (plan: string) => void;
  error?: string | null;
}) {
  const plan = planOf(meta, value);
  const count = (value: number, unit: string) => (value ? `${value.toLocaleString("en-US")} ${unit}` : null);
  const hint = plan
    ? plan.key === "enterprise"
      ? "Custom volume, every channel"
      : [
          count(plan.included_minutes, "min"),
          count(plan.included_chats, "chats"),
          count(plan.included_sms, "texts"),
          count(plan.phone_numbers, plan.phone_numbers === 1 ? "number" : "numbers"),
        ]
          .filter(Boolean)
          .join(" · ")
    : undefined;
  return (
    <FormField id={id} label="Plan" hint={hint} error={error}>
      <Select {...fieldProps(id, error, hint)} value={value} disabled={!meta} onChange={(event) => onChange(event.target.value)}>
        {!meta && <option value={value}>{value || "Loading…"}</option>}
        {meta?.plans.map((item) => (
          <option key={item.key} value={item.key}>
            {item.name} — {planPrice(item)}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

export function LanguageField({ id, meta, value, onChange }: { id: string; meta: AdminMeta | null; value: Language; onChange: (value: Language) => void }) {
  const languages = meta?.languages?.length
    ? meta.languages
    : [
        { code: "en" as Language, label: "English" },
        { code: "bn" as Language, label: "Bangla (বাংলা)" },
      ];
  const hint = "The agent's first language. Callers can still switch.";
  return (
    <FormField id={id} label="Language" hint={hint}>
      <Select {...fieldProps(id, null, hint)} value={value} onChange={(event) => onChange(event.target.value as Language)}>
        {languages.map((language) => (
          <option key={language.code} value={language.code}>
            {language.label}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

export function PersonaField({ id, value, onChange }: { id: string; value: VoicePersona; onChange: (value: VoicePersona) => void }) {
  return (
    <FormField id={id} label="Voice persona">
      <Select id={id} value={value} onChange={(event) => onChange(event.target.value as VoicePersona)}>
        <option value="female">Female voice</option>
        <option value="male">Male voice</option>
      </Select>
    </FormField>
  );
}

/** Business-engine picker for new accounts: one card per vertical, with its description. */
export function VerticalPicker({
  name,
  verticals,
  value,
  onChange,
  error,
}: {
  name: string;
  verticals: VerticalSpec[];
  value: VerticalKey | "";
  onChange: (value: VerticalKey) => void;
  error?: string | null;
}) {
  const noteId = `${name}-note`;
  const errorId = `${name}-error`;
  return (
    <fieldset className="min-w-0" aria-describedby={error ? `${errorId} ${noteId}` : noteId}>
      <legend className="text-[13.5px] font-semibold text-muted-foreground">
        Business type
        <span className="text-destructive" aria-hidden="true">
          {" "}
          *
        </span>
        <span className="sr-only"> (required)</span>
      </legend>
      <p id={noteId} className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Lock className="h-3 w-3 shrink-0" aria-hidden="true" />
        Fixed after creation — it decides the agent&apos;s scripts, records and catalog.
      </p>
      {verticals.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">Loading business types…</p>
      ) : (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {verticals.map((spec) => (
            <label
              key={spec.key}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors hover:bg-surface",
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                value === spec.key ? "border-primary bg-accent/50" : "border-border",
              )}
            >
              <input
                type="radio"
                name={name}
                value={spec.key}
                checked={value === spec.key}
                onChange={() => onChange(spec.key)}
                aria-invalid={error ? true : undefined}
                className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
              />
              <span className="min-w-0">
                <span className="block font-semibold">{t(spec.label, spec.key)}</span>
                <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{t(spec.description)}</span>
              </span>
            </label>
          ))}
        </div>
      )}
      {error && (
        <p id={errorId} className="mt-1.5 text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </fieldset>
  );
}
