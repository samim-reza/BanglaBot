"use client";

import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { CatalogOptions, CatalogTier } from "@/services/api/admin/plans";

import type { CatalogErrors } from "./catalog-errors";
import { ChipSelect, humanKey, Labeled, NumCell, SwitchCell, TextCell } from "./cells";

/** The tier fields that don't fit the table row. */
export function TierDetails({
  tier,
  options,
  errors,
  index,
  disabled,
  onChange,
}: {
  tier: CatalogTier;
  options: CatalogOptions;
  errors: CatalogErrors;
  index: number;
  disabled: boolean;
  onChange: (patch: Partial<CatalogTier>) => void;
}) {
  const err = (field: string) => errors.fields[`tiers.${index}.${field}`];
  const limits = tier.limits;
  const setLimits = (patch: Partial<CatalogTier["limits"]>) => onChange({ limits: { ...limits, ...patch } });
  const asChips = (keys: string[]) => keys.map((key) => ({ key, label: humanKey(key) }));

  return (
    <div className="grid gap-4 py-2 md:grid-cols-2 xl:grid-cols-4">
      <Labeled label="Tagline" className="md:col-span-2">
        <TextCell value={tier.tagline} onChange={(v) => onChange({ tagline: v })} label="Tagline" disabled={disabled} error={err("tagline")} />
      </Labeled>
      <Labeled label="Product">
        <Select className="h-8 text-[13px]" value={tier.product} disabled={disabled} onChange={(e) => onChange({ product: e.target.value as CatalogTier["product"] })}>
          {options.products.map((p) => (
            <option key={p} value={p}>
              {humanKey(p)}
            </option>
          ))}
        </Select>
      </Labeled>
      <div className="grid grid-cols-3 gap-2">
        <Labeled label="$/min over" hint="Overage price per minute">
          <NumCell value={tier.overage_per_minute} onChange={(n) => onChange({ overage_per_minute: n })} label="Overage per minute" step="0.01" className="w-full" disabled={disabled} />
        </Labeled>
        <Labeled label="Languages">
          <NumCell value={tier.included_languages} onChange={(n) => onChange({ included_languages: n })} label="Included languages" className="w-full" disabled={disabled} />
        </Labeled>
        <Labeled label="Trial days" hint="0 = a normal billing period">
          <NumCell value={tier.trial_days} onChange={(n) => onChange({ trial_days: n })} label="Trial days" className="w-full" disabled={disabled} />
        </Labeled>
      </div>

      <Labeled label="Channels" className="md:col-span-2">
        <ChipSelect options={options.channels} value={tier.channels} onChange={(v) => onChange({ channels: v })} label="Channels" disabled={disabled} />
      </Labeled>
      <Labeled label="Includes" className="md:col-span-2">
        <ChipSelect options={asChips(options.features)} value={tier.includes} onChange={(v) => onChange({ includes: v })} label="Included features" disabled={disabled} emptyLabel="None" />
      </Labeled>

      <Labeled label="Concurrent calls">
        <NumCell value={limits.max_concurrent_calls} onChange={(n) => setLimits({ max_concurrent_calls: n })} label="Concurrent calls" className="w-full" disabled={disabled} />
      </Labeled>
      <Labeled label="Flow editing" hint="lines = reword only · full = steps too">
        <Select className="h-8 text-[13px]" value={limits.flow_editing} disabled={disabled} onChange={(e) => setLimits({ flow_editing: e.target.value })}>
          {options.flow_editing.map((level) => (
            <option key={level} value={level}>
              {humanKey(level)}
            </option>
          ))}
        </Select>
      </Labeled>
      <div className="flex flex-wrap items-end gap-4 md:col-span-2">
        {(["payments", "custom_fields", "api_webhooks"] as const).map((key) => (
          <span key={key} className="flex items-center gap-2 text-[13px]">
            <SwitchCell checked={Boolean(limits[key])} onChange={(v) => setLimits({ [key]: v })} label={humanKey(key)} disabled={disabled} />
            {humanKey(key)}
          </span>
        ))}
        <span className="flex items-center gap-2 text-[13px]">
          <SwitchCell checked={tier.highlight} onChange={(v) => onChange({ highlight: v })} label="Highlight" disabled={disabled} />
          Highlight
        </span>
      </div>

      <Labeled label="Business types" className="md:col-span-2">
        <ChipSelect options={asChips(options.verticals)} value={tier.verticals} onChange={(v) => onChange({ verticals: v })} label="Business types" disabled={disabled} emptyLabel="All" />
      </Labeled>
      <Labeled label="Bullets" hint="One per line, 80 characters max" className="md:col-span-2">
        <Textarea
          className="min-h-[72px] text-[13px]"
          value={tier.features.join("\n")}
          disabled={disabled}
          onChange={(e) => onChange({ features: e.target.value.split("\n") })}
          onBlur={(e) => onChange({ features: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })}
        />
      </Labeled>
    </div>
  );
}
