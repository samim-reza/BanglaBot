"use client";

/** The drawer's Lines tab: one text box per spoken line, with variable chips and a counter. */

import { useRef } from "react";
import { RotateCcw } from "lucide-react";

import { InfoTip } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { FlowFieldError, FlowLineSpec } from "@/services/api";

import { FieldErrors, LockBadge } from "./bits";
import { squash, withLine } from "./model";
import { errorsFor, isLocked } from "./rules";
import type { ReadyFlow } from "./step-list";

const PLACEHOLDER = /\{([^{}]*)\}/g;

function LineField({
  id,
  spec,
  value,
  base,
  locked,
  errors,
  onChange,
}: {
  id: string;
  spec: FlowLineSpec;
  value: string;
  base: string;
  locked: boolean;
  errors: FlowFieldError[];
  onChange: (text: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const length = squash(value).length;
  const over = length > spec.max_chars;
  const missing = value.trim() ? spec.required_vars.filter((name) => !value.includes(`{${name}}`)) : [];
  const unknown = [...value.matchAll(PLACEHOLDER)].map((match) => match[1]).filter((name) => !spec.variables.includes(name));
  const changed = squash(value) !== squash(base);
  const invalid = over || missing.length > 0 || unknown.length > 0 || errors.length > 0;

  const insert = (name: string) => {
    const element = ref.current;
    const start = element?.selectionStart ?? value.length;
    const end = element?.selectionEnd ?? value.length;
    const token = `{${name}}`;
    onChange(`${value.slice(0, start)}${token}${value.slice(end)}`);
    window.requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(start + token.length, start + token.length);
    });
  };

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={id} className="text-[13.5px] font-semibold text-muted-foreground">
          {spec.label}
        </label>
        <div className="flex items-center gap-2">
          {locked && <LockBadge />}
          {changed && !locked && (
            <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => onChange(base)}>
              <RotateCcw className="h-3 w-3" aria-hidden />
              Reset
            </Button>
          )}
          <span className={cn("text-xs tabular-nums", over ? "font-semibold text-destructive" : "text-muted-foreground")} aria-live="polite">
            {length} / {spec.max_chars}
          </span>
        </div>
      </div>
      <Textarea
        ref={ref}
        id={id}
        rows={2}
        value={value}
        placeholder={base}
        disabled={locked}
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-problems` : undefined}
        className={cn(invalid && "border-destructive")}
        onChange={(event) => onChange(event.target.value)}
      />
      {spec.variables.length > 0 && !locked && (
        <div className="flex flex-wrap items-center gap-1" aria-label="Insert a detail">
          {spec.variables.map((name) => {
            const required = spec.required_vars.includes(name);
            return (
              <button
                key={name}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => insert(name)}
                title={required ? "Must stay in the line" : "Insert"}
                className={cn(
                  "rounded-full border px-2 py-0.5 font-mono text-[11.5px] transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  required ? "border-primary/60 text-primary-dark dark:text-primary" : "border-border text-muted-foreground",
                )}
              >
                {`{${name}}`}
              </button>
            );
          })}
        </div>
      )}
      <div id={`${id}-problems`} className="space-y-0.5">
        {missing.length > 0 && <p className="text-xs font-medium text-destructive">Keep {missing.map((name) => `{${name}}`).join(", ")}</p>}
        {unknown.length > 0 && <p className="text-xs font-medium text-destructive">Unknown {unknown.map((name) => `{${name}}`).join(", ")}</p>}
        <FieldErrors errors={errors} />
      </div>
    </div>
  );
}

export function LinesEditor({ state, skillKey, lang }: { state: ReadyFlow; skillKey: string; lang: string }) {
  const { model, draft, locked, errors, update } = state;
  const skill = model.skills[skillKey];
  const step = draft.steps[skillKey];
  if (!skill || !step) return null;
  return (
    <div className="space-y-5">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        Said word for word
        <InfoTip label="About lines">Empty = the default. Click a detail like {"{business}"} to insert it; outlined ones must stay.</InfoTip>
      </p>
      {skill.lines.map((spec) => {
        const path = `steps.${skillKey}.lines.${lang}.${spec.key}`;
        return (
          <LineField
            key={`${lang}:${spec.key}`}
            id={`line-${skillKey}-${lang}-${spec.key}`}
            spec={spec}
            value={step.lines[lang]?.[spec.key] ?? ""}
            base={model.baseline.steps[skillKey]?.lines[lang]?.[spec.key] ?? ""}
            locked={isLocked(locked, path)}
            errors={errorsFor(errors, path)}
            onChange={(text) => update(path, (current) => withLine(current, skillKey, lang, spec.key, text))}
          />
        );
      })}
    </div>
  );
}
