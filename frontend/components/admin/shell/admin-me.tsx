"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { adminToken, isApiRequestError } from "@/services/api";
import { adminUsersApi, type AdminMe } from "@/services/api/admin/users";

import { PERMISSIONS, type Permission } from "./permissions";

type AdminMeState = {
  me: AdminMe | null;
  /** True until /me has answered (or failed). */
  loading: boolean;
  can: (permission: Permission) => boolean;
  reload: () => Promise<void>;
};

const AdminMeContext = createContext<AdminMeState>({ me: null, loading: true, can: () => false, reload: async () => undefined });

/**
 * The signed-in admin (GET /api/admin/users/me) for role-aware navigation and actions. Loaded once
 * per sign-in; if /me itself fails for a reason other than a dead session, the console stays usable
 * and the API's own 403s are the guard.
 */
export function AdminMeProvider({ enabled, children }: { enabled: boolean; children: React.ReactNode }) {
  const [me, setMe] = useState<AdminMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(async () => {
    if (!adminToken()) return;
    try {
      setMe(await adminUsersApi.me());
      setFailed(false);
    } catch (err) {
      if (!(isApiRequestError(err) && err.status === 401)) setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setMe(null);
      setLoading(true);
      setFailed(false);
      return;
    }
    void reload();
  }, [enabled, reload]);

  const value = useMemo<AdminMeState>(
    () => ({
      me,
      loading,
      can: (permission) => (me ? (PERMISSIONS[permission] as readonly string[]).includes(me.role) : failed),
      reload,
    }),
    [me, loading, failed, reload],
  );

  return <AdminMeContext.Provider value={value}>{children}</AdminMeContext.Provider>;
}

export function useAdminMe(): AdminMeState {
  return useContext(AdminMeContext);
}
