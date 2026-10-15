"use client";

import { useCallback, useEffect, useState } from "react";

import { adminApi, formatApiError, isApiRequestError, type AdminMerchantDetail } from "@/services/api";

/** One account's detail (GET /api/admin/merchants/{id}). */
export function useAccount(id: string) {
  const [detail, setDetail] = useState<AdminMerchantDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setDetail(await adminApi.merchant(id));
      setError(null);
      setNotFound(false);
    } catch (err) {
      if (isApiRequestError(err) && err.status === 404) setNotFound(true);
      else setError(formatApiError(err, "Could not load this account."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  return { detail, error, notFound, loading, reload: load };
}
