"use client";

import { Toggle } from "@/components/agent-flow/bits";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { t } from "@/lib/vertical";
import type { FlowOptionSpec } from "@/services/api/agentFlow";

import { describeValue } from "./flow-paths";

/** An option's control. Structured types (lists, intake fields) are shown, not edited, here. */
export function OptionControl({
  spec,
  value,
  disabled,
  onChange,
}: {
  spec: FlowOptionSpec;
  value: unknown;
  disabled: boolean;
  onChange: (value: unknown) => void;
}) {
  const label = t(spec.label, spec.key);
  switch (spec.type) {
    case "bool":
      return <Toggle checked={Boolean(value)} onChange={onChange} label={label} disabled={disabled} />;
    case "select":
      return (
        <Select className="h-8 w-full text-[13.5px] sm:w-56" aria-label={label} value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {value === undefined || value === null || value === "" ? <option value="">—</option> : null}
          {spec.options.map((option) => (
            <option key={option.value} value={option.value}>
              {t(option.label, option.value)}
            </option>
          ))}
        </Select>
      );
    case "number":
    case "money":
      return (
        <Input
          type="number"
          className="h-8 w-full text-[13.5px] sm:w-32"
          aria-label={label}
          value={value === undefined || value === null ? "" : String(value)}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        />
      );
    case "text":
    case "textarea":
    case "phone":
    case "date":
    case "time":
      return (
        <Input
          className="h-8 w-full text-[13.5px] sm:w-56"
          aria-label={label}
          value={typeof value === "string" ? value : ""}
          placeholder={spec.placeholder || undefined}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    default:
      return (
        <span className="text-sm text-muted-foreground" title="Edited by the owner in their portal">
          {describeValue(value, spec)}
        </span>
      );
  }
}
