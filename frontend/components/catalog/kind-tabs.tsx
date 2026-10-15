"use client";

import { useRef, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { CatalogKindSpec } from "@/services/api";

/** Underline tab bar, one tab per catalog kind (←/→, Home/End move between tabs). */
export function KindTabs({ kinds, active, onSelect }: { kinds: CatalogKindSpec[]; active: string; onSelect: (kind: string) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = kinds.findIndex((spec) => spec.kind === active);
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % kinds.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + kinds.length) % kinds.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = kinds.length - 1;
    else return;
    event.preventDefault();
    const kind = kinds[next].kind;
    onSelect(kind);
    refs.current[kind]?.focus();
  };

  return (
    <div role="tablist" aria-label="Catalog" className="-mx-4 flex gap-1 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
      {kinds.map((spec) => {
        const selected = spec.kind === active;
        return (
          <button
            key={spec.kind}
            ref={(node) => {
              refs.current[spec.kind] = node;
            }}
            type="button"
            role="tab"
            id={`catalog-tab-${spec.kind}`}
            aria-controls={`catalog-panel-${spec.kind}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(spec.kind)}
            onKeyDown={onKeyDown}
            className={cn(
              "-mb-px inline-flex h-10 shrink-0 items-center whitespace-nowrap border-b-2 px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              selected ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t(spec.label_plural, spec.kind)}
          </button>
        );
      })}
    </div>
  );
}
