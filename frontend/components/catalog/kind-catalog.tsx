"use client";

import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";

import type { CatalogKindSpec } from "@/services/api";

import { CatalogBoard } from "./catalog-board";
import { KindTabs } from "./kind-tabs";

/** Several catalog kinds: tabs (kept in `?kind=`) over one board per kind. Render inside <Suspense> (useSearchParams). */
export function KindCatalog({ kinds }: { kinds: CatalogKindSpec[] }) {
  const searchParams = useSearchParams();
  const resolve = useCallback((value: string | null) => kinds.find((spec) => spec.kind === value)?.kind ?? null, [kinds]);

  // The address decides the tab (?kind=…); follow it when it changes.
  const urlKind = searchParams.get("kind");
  const [active, setActive] = useState<string>(() => resolve(urlKind) ?? kinds[0].kind);
  const [seenUrlKind, setSeenUrlKind] = useState(urlKind);
  if (urlKind !== seenUrlKind) {
    setSeenUrlKind(urlKind);
    const next = resolve(urlKind);
    if (next && next !== active) setActive(next);
  }

  const select = useCallback((kind: string) => {
    setActive(kind);
    const params = new URLSearchParams(window.location.search);
    params.set("kind", kind);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, []);

  const index = Math.max(0, kinds.findIndex((spec) => spec.kind === active));
  const spec = kinds[index];

  return (
    <>
      <KindTabs kinds={kinds} active={spec.kind} onSelect={select} />
      <div role="tabpanel" id={`catalog-panel-${spec.kind}`} aria-labelledby={`catalog-tab-${spec.kind}`}>
        <CatalogBoard key={spec.kind} spec={spec} primary={index === 0} multi />
      </div>
    </>
  );
}
