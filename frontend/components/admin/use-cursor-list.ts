"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { formatApiError } from "@/services/api";
import type { CursorPage } from "@/services/api/admin/common";

/**
 * A server-paginated (cursor) list: the first page loads whenever `key` changes (e.g. the
 * filters), `loadMore` appends the next page. Stale responses from an older key are dropped.
 */
export function useCursorList<T>(fetchPage: (cursor: string) => Promise<CursorPage<T>>, key: string, errorText: string) {
  const [items, setItems] = useState<T[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchRef = useRef(fetchPage);
  const generation = useRef(0);

  useEffect(() => {
    fetchRef.current = fetchPage;
  });

  const reload = useCallback(async () => {
    const mine = ++generation.current;
    setLoading(true);
    try {
      const page = await fetchRef.current("");
      if (mine !== generation.current) return;
      setItems(page.items);
      setNext(page.next_cursor);
      setError(null);
    } catch (err) {
      if (mine !== generation.current) return;
      setItems([]);
      setNext(null);
      setError(formatApiError(err, errorText));
    } finally {
      if (mine === generation.current) setLoading(false);
    }
  }, [errorText]);

  useEffect(() => {
    void reload();
  }, [key, reload]);

  const loadMore = useCallback(async () => {
    if (!next || loadingMore) return;
    const mine = generation.current;
    setLoadingMore(true);
    try {
      const page = await fetchRef.current(next);
      if (mine !== generation.current) return;
      setItems((current) => [...current, ...page.items]);
      setNext(page.next_cursor);
      setError(null);
    } catch (err) {
      if (mine === generation.current) setError(formatApiError(err, errorText));
    } finally {
      setLoadingMore(false);
    }
  }, [next, loadingMore, errorText]);

  return { items, setItems, hasMore: Boolean(next), loading, loadingMore, error, reload, loadMore };
}
