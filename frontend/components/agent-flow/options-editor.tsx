"use client";

/** The drawer's Options tab: the step's settings (schema form) plus the intake field editors. */

import Link from "next/link";

import { InfoTip } from "@/components/portal/kit";
import { SchemaFields } from "@/components/schema-form";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import type { FieldSpec, FlowOptionSpec } from "@/services/api";

import { CustomFieldsEditor } from "./custom-fields-editor";
import { FieldErrors, LockBadge } from "./bits";
import { IntakeFieldsTable } from "./intake-fields-table";
import { withOption } from "./model";
import { UPGRADE_LINES_ONLY, errorsFor, isLocked } from "./rules";
import type { ReadyFlow } from "./step-list";

const WIDE = new Set(["textarea", "list", "days", "multiselect", "fields", "custom_fields"]);

/** Options that only matter for one value of a sibling option (e.g. the deposit when the amount is a deposit). */
const SHOW_WHEN: Record<string, [string, string]> = {
  deposit_amount: ["amount_source", "deposit"],
  fixed_amount: ["amount_source", "fixed"],
  hold_minutes: ["mode", "online_required"],
};

function OptionLabel({ spec }: { spec: FlowOptionSpec }) {
  const label = t(spec.label, spec.key);
  const help = t(spec.help);
  return (
    <span className="flex items-center gap-1.5 text-[13.5px] font-semibold text-muted-foreground">
      {label}
      {help && <InfoTip label={`About ${label.toLowerCase()}`}>{help}</InfoTip>}
    </span>
  );
}

export function OptionsEditor({ state, skillKey }: { state: ReadyFlow; skillKey: string }) {
  const { merchant, entitlements } = useWorkspace();
  const { model, draft, locked, errors, update } = state;
  const skill = model.skills[skillKey];
  const step = draft.steps[skillKey];
  if (!skill || !step) return null;
  const linesOnly = model.editing === "lines";
  const has = (key: string) => skill.options.some((spec) => spec.key === key);
  const visible = skill.options.filter((spec) => {
    const rule = SHOW_WHEN[spec.key];
    return !rule || !has(rule[0]) || step.options[rule[0]] === rule[1];
  });

  return (
    <div className="space-y-4">
      {linesOnly && (
        <p className="rounded-md border border-border bg-surface px-3 py-2 text-xs text-muted-foreground">
          {UPGRADE_LINES_ONLY}{" "}
          <Link href="/plan" className="font-medium text-primary-dark hover:underline dark:text-primary">
            Upgrade
          </Link>
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {visible.map((spec) => {
          const path = `steps.${skillKey}.options.${spec.key}`;
          const lockedHere = isLocked(locked, path);
          const disabled = linesOnly || lockedHere;
          const onChange = (value: unknown) => update(path, (current) => withOption(current, skillKey, spec.key, value));
          const wide = WIDE.has(spec.type) && "sm:col-span-2";

          if (spec.type === "fields" || spec.type === "custom_fields") {
            const noCustom = spec.type === "custom_fields" && entitlements.capabilities?.custom_fields === false;
            return (
              <div key={spec.key} className={cn("space-y-2", wide)}>
                <div className="flex items-center justify-between gap-2">
                  <OptionLabel spec={spec} />
                  {lockedHere && <LockBadge />}
                </div>
                {spec.type === "fields" ? (
                  <>
                    <IntakeFieldsTable value={step.options[spec.key]} defaults={skill.defaults[spec.key]} disabled={disabled} onChange={onChange} />
                    <FieldErrors errors={errorsFor(errors, path)} />
                  </>
                ) : (
                  <CustomFieldsEditor
                    value={step.options[spec.key]}
                    path={path}
                    errors={errorsFor(errors, path)}
                    disabled={disabled || noCustom}
                    reason={noCustom ? "Not in your plan — upgrade to add questions." : null}
                    onChange={onChange}
                  />
                )}
              </div>
            );
          }

          return (
            <div key={spec.key} className={cn("space-y-1.5", wide)}>
              <SchemaFields
                specs={[spec as FieldSpec]}
                values={step.options}
                timezone={merchant.timezone}
                disabled={disabled}
                className="block"
                onChange={(values) => onChange(values[spec.key])}
              />
              {lockedHere && <LockBadge />}
              <FieldErrors errors={errorsFor(errors, path)} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
