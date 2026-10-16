"use client";

/** Side panel for one step: its spoken lines and its options. */

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";

import { LockBadge } from "./bits";
import { LinesEditor } from "./lines-editor";
import { OptionsEditor } from "./options-editor";
import { errorsFor, lockedUnder } from "./rules";
import type { ReadyFlow } from "./step-list";

type Tab = "lines" | "options";

/** Lines are edited in English, the only call language. */
const LINE_LANGUAGE = "en";

export function StepDrawer({ state, skillKey, onClose }: { state: ReadyFlow; skillKey: string; onClose: () => void }) {
  const skill = state.model.skills[skillKey];
  const tabs: Tab[] = [...(skill?.lines.length ? (["lines"] as Tab[]) : []), ...(skill?.options.length ? (["options"] as Tab[]) : [])];
  const [tab, setTab] = useState<Tab>(tabs[0] ?? "lines");
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panelRef.current?.querySelector<HTMLElement>("[data-drawer-close]")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  if (!skill) return null;
  const label = t(skill.label, skill.key);
  const path = `steps.${skillKey}`;
  const count = (prefix: string) => errorsFor(state.errors, prefix).length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" tabIndex={-1} aria-label="Close" className="absolute inset-0 bg-foreground/30" onClick={onClose} />
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="step-drawer-title" className="relative flex h-full w-full max-w-xl flex-col border-l border-border bg-card shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id="step-drawer-title" className="flex flex-wrap items-center gap-2 text-base font-semibold">
              {label}
              {lockedUnder(state.locked, path) && <LockBadge />}
            </h2>
            {t(skill.description) && <p className="mt-0.5 text-sm text-muted-foreground">{t(skill.description)}</p>}
          </div>
          <button
            type="button"
            data-drawer-close
            aria-label="Close"
            onClick={onClose}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {tabs.length > 1 && (
          <div role="tablist" aria-label={label} className="flex gap-1 border-b border-border px-5">
            {tabs.map((key) => {
              const errors = count(`${path}.${key}`);
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={cn(
                    "-mb-px inline-flex h-10 items-center gap-1.5 border-b-2 px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    tab === key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {key === "lines" ? "Lines" : "Options"}
                  {errors > 0 && <span className="h-1.5 w-1.5 rounded-full bg-destructive" aria-label={`${errors} to fix`} />}
                </button>
              );
            })}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {tab === "lines" ? (
            <div className="space-y-4">
              <LinesEditor state={state} skillKey={skillKey} lang={LINE_LANGUAGE} />
            </div>
          ) : (
            <OptionsEditor state={state} skillKey={skillKey} />
          )}
        </div>
        <div className="border-t border-border px-5 py-3 text-right">
          <button type="button" onClick={onClose} className="text-sm font-semibold text-primary-dark hover:underline dark:text-primary">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
