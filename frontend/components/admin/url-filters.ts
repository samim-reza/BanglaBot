"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * List filters that live in the URL query (`?merchant_id=…&status=…&page=2`),
 * so deep links, reloads and Back all land on the same view. Must render
 * inside a <Suspense> boundary (useSearchParams).
 */
export function useUrlFilters<K extends string>(keys: readonly K[]) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();

  const values = useMemo(() => {
    const params = new URLSearchParams(query);
    return Object.fromEntries(keys.map((key) => [key, params.get(key) ?? ""])) as Record<K, string>;
    // `keys` is a module-level constant at every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const setFilters = useCallback(
    (patch: Partial<Record<K, string | number | null>>) => {
      const params = new URLSearchParams(query);
      for (const [key, value] of Object.entries(patch) as [string, string | number | null | undefined][]) {
        if (value === null || value === undefined || value === "" || (key === "page" && Number(value) <= 1)) params.delete(key);
        else params.set(key, String(value));
      }
      const next = params.toString();
      router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    },
    [query, pathname, router],
  );

  return [values, setFilters] as const;
}

/** A positive page number from the query (defaults to 1). */
export function pageFrom(value: string): number {
  const page = Number.parseInt(value, 10);
  return Number.isFinite(page) && page > 0 ? page : 1;
}
