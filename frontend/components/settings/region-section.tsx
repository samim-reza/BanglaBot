"use client";

import { FormEvent, useMemo } from "react";
import { Globe } from "lucide-react";

import { InfoTip, SectionCard, same, useDraft } from "@/components/portal/kit";
import { FormRow, SaveBar, useReportDirty, useSaver, validTimeZone } from "@/components/settings/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatInZone, money } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { merchantApi, type Merchant } from "@/services/api";

const COMMON_TIME_ZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Phoenix",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "America/Toronto",
  "America/Vancouver",
  "America/Halifax",
  "America/Mexico_City",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Dublin",
  "Europe/Lisbon",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Madrid",
  "Europe/Rome",
  "Europe/Amsterdam",
  "Europe/Istanbul",
  "Africa/Cairo",
  "Africa/Lagos",
  "Africa/Nairobi",
  "Africa/Johannesburg",
  "Asia/Riyadh",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Dhaka",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Hong_Kong",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Australia/Perth",
  "Australia/Brisbane",
  "Australia/Sydney",
  "Australia/Melbourne",
  "Pacific/Auckland",
];

type RegionForm = { timezone: string; currency: string; emergency_number: string };

function regionFrom(merchant: Merchant): RegionForm {
  return { timezone: merchant.timezone ?? "", currency: merchant.currency ?? "", emergency_number: merchant.emergency_number ?? "" };
}

export function RegionSection({ onSaved }: { onSaved?: () => void }) {
  const { merchant, regions, refresh } = useWorkspace();
  const source = useMemo(() => regionFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("region", dirty);

  const region = regions.find((item) => item.code === merchant.region);
  const zoneOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: { value: string; label: string }[] = [];
    for (const item of regions) {
      if (!seen.has(item.timezone)) {
        seen.add(item.timezone);
        out.push({ value: item.timezone, label: item.label });
      }
    }
    for (const zone of COMMON_TIME_ZONES) {
      if (!seen.has(zone)) {
        seen.add(zone);
        out.push({ value: zone, label: "" });
      }
    }
    return out;
  }, [regions]);

  const zoneOk = validTimeZone(draft.timezone);
  const currencyOk = /^[A-Z]{3}$/.test(draft.currency);
  const emergencyDigits = draft.emergency_number.replace(/\D/g, "");
  const emergencyOk = emergencyDigits.length >= 2 && emergencyDigits.length <= 8;
  const regionDefaults: RegionForm | null = region
    ? { timezone: region.timezone, currency: region.currency, emergency_number: region.emergency }
    : null;

  const patch = (values: Partial<RegionForm>) => setDraft((current) => ({ ...current, ...values }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!zoneOk) return setError("Choose a valid time zone, e.g. America/New_York.");
    if (!currencyOk) return setError("Currency must be a 3-letter code, e.g. USD.");
    if (!emergencyOk) return setError("The emergency number must be 2–8 digits, e.g. 911, 999 or 112.");
    void run(async () => {
      const updated = await merchantApi.updateMe({
        timezone: draft.timezone.trim(),
        currency: draft.currency,
        emergency_number: emergencyDigits,
      });
      commit(regionFrom(updated));
      await refresh();
      onSaved?.();
    }, "Region settings saved.");
  };

  return (
    <SectionCard id="region" icon={Globe} title="Region & locale" description="Clock, currency and emergency number.">
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-[13.5px] font-semibold text-muted-foreground">
              Region
              <InfoTip label="About region">Set by your admin. It decides the phone number format and the agent&apos;s accent.</InfoTip>
            </p>
            <p className="mt-0.5 font-medium">
              {region?.label ?? merchant.region} <span className="text-muted-foreground">({merchant.region})</span>
            </p>
          </div>
          {regionDefaults && !same(draft, regionDefaults) && (
            <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={() => patch(regionDefaults)}>
              Use region defaults
            </Button>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <FormRow
            id="timezone"
            label="Time zone"
            className="sm:col-span-3"
            hint={zoneOk ? `Now: ${formatInZone(new Date().toISOString(), draft.timezone.trim())}` : "e.g. Europe/London"}
          >
            <Input
              id="timezone"
              list="timezone-options"
              value={draft.timezone}
              maxLength={64}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={!zoneOk}
              aria-describedby="timezone-hint"
              className={cn(!zoneOk && "border-destructive")}
              onChange={(e) => patch({ timezone: e.target.value })}
            />
            <datalist id="timezone-options">
              {zoneOptions.map((zone) => (
                <option key={zone.value} value={zone.value}>
                  {zone.label}
                </option>
              ))}
            </datalist>
          </FormRow>
          <FormRow id="currency" label="Currency" hint={currencyOk ? `e.g. ${money(1234.5, draft.currency)}` : "3-letter code, e.g. USD"}>
            <Input
              id="currency"
              value={draft.currency}
              maxLength={3}
              autoComplete="off"
              spellCheck={false}
              className={cn("uppercase", !currencyOk && "border-destructive")}
              aria-invalid={!currencyOk}
              aria-describedby="currency-hint"
              onChange={(e) => patch({ currency: e.target.value.toUpperCase().replace(/[^A-Z]/g, "") })}
            />
          </FormRow>
          <FormRow
            id="emergency_number"
            label="Emergency number"
            className="sm:col-span-2"
            info="The agent tells callers to dial this in an emergency (gas smell, chest pain, fire)."
          >
            <Input
              id="emergency_number"
              inputMode="numeric"
              value={draft.emergency_number}
              maxLength={8}
              className={cn(!emergencyOk && "border-destructive")}
              aria-invalid={!emergencyOk}
              onChange={(e) => patch({ emergency_number: e.target.value.replace(/\D/g, "") })}
            />
          </FormRow>
        </div>

        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} />
      </form>
    </SectionCard>
  );
}
