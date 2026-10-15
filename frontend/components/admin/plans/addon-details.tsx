"use client";

import { X } from "lucide-react";

import { Select } from "@/components/ui/select";
import type { CatalogAddon, CatalogOptions } from "@/services/api/admin/plans";

import type { CatalogErrors } from "./catalog-errors";
import { ChipSelect, humanKey, Labeled, NumCell, SwitchCell, TextCell } from "./cells";

/** The add-on fields that don't fit the table row. */
export function AddonDetails({
  addon,
  options,
  errors,
  index,
  disabled,
  onChange,
}: {
  addon: CatalogAddon;
  options: CatalogOptions;
  errors: CatalogErrors;
  index: number;
  disabled: boolean;
  onChange: (patch: Partial<CatalogAddon>) => void;
}) {
  const err = (field: string) => errors.fields[`addons.${index}.${field}`];
  const grants = Object.entries(addon.grants ?? {});
  const unused = options.grants.filter((key) => !(key in (addon.grants ?? {})));
  const setGrant = (key: string, amount: number | null) => {
    const next = { ...addon.grants };
    if (amount === null) delete next[key];
    else next[key] = amount;
    onChange({ grants: next });
  };
  const asChips = (keys: string[]) => keys.map((key) => ({ key, label: humanKey(key) }));

  return (
    <div className="grid gap-4 py-2 md:grid-cols-2 xl:grid-cols-4">
      <Labeled label="Summary" className="md:col-span-2">
        <TextCell value={addon.summary} onChange={(v) => onChange({ summary: v })} label="Summary" disabled={disabled} error={err("summary")} />
      </Labeled>
      <Labeled label="Switches on channel">
        <Select className="h-8 text-[13px]" value={addon.channel} disabled={disabled} onChange={(e) => onChange({ channel: e.target.value })}>
          <option value="">—</option>
          {options.channels.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </Select>
      </Labeled>
      <Labeled label="Switches on feature">
        <Select className="h-8 text-[13px]" value={addon.feature} disabled={disabled} onChange={(e) => onChange({ feature: e.target.value })}>
          <option value="">—</option>
          {[...options.features, ...options.capabilities].map((f) => (
            <option key={f} value={f}>
              {humanKey(f)}
            </option>
          ))}
        </Select>
      </Labeled>

      <div className="space-y-2 md:col-span-2">
        <span className="text-xs font-semibold text-muted-foreground" title="Extra monthly allowance per unit">
          Grants per unit
        </span>
        <ul className="flex flex-wrap gap-2">
          {grants.map(([key, amount]) => (
            <li key={key} className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1">
              <span className="text-[13px]">{humanKey(key)}</span>
              <NumCell value={amount} onChange={(n) => setGrant(key, n)} label={`${key} per unit`} className="w-20" disabled={disabled} />
              {!disabled && (
                <button type="button" aria-label={`Remove ${key}`} className="text-muted-foreground hover:text-destructive" onClick={() => setGrant(key, null)}>
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
          {!disabled && unused.length > 0 && (
            <li>
              <Select
                className="h-8 w-40 text-[13px]"
                aria-label="Add a grant"
                value=""
                onChange={(e) => e.target.value && setGrant(e.target.value, 1)}
              >
                <option value="">+ Grant…</option>
                {unused.map((key) => (
                  <option key={key} value={key}>
                    {humanKey(key)}
                  </option>
                ))}
              </Select>
            </li>
          )}
          {grants.length === 0 && disabled && <li className="text-sm text-muted-foreground">None</li>}
        </ul>
        {err("grants") && <p className="text-xs font-medium text-destructive">{err("grants")}</p>}
      </div>
      <div className="flex flex-wrap items-end gap-4">
        <span className="flex items-center gap-2 text-[13px]">
          <SwitchCell checked={addon.stackable} onChange={(v) => onChange({ stackable: v })} label="Stackable" disabled={disabled} />
          Stackable
        </span>
        <Labeled label="Max qty">
          <NumCell value={addon.max_quantity} onChange={(n) => onChange({ max_quantity: n })} label="Max quantity" disabled={disabled || !addon.stackable} />
        </Labeled>
      </div>
      <Labeled label="Products">
        <ChipSelect options={asChips(options.products)} value={addon.products} onChange={(v) => onChange({ products: v })} label="Products" disabled={disabled} emptyLabel="Any" />
      </Labeled>
      <Labeled label="Business types" className="md:col-span-2">
        <ChipSelect options={asChips(options.verticals)} value={addon.verticals} onChange={(v) => onChange({ verticals: v })} label="Business types" disabled={disabled} emptyLabel="All" />
      </Labeled>
    </div>
  );
}
