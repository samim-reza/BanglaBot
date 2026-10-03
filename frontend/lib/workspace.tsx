"use client";

/**
 * The signed-in account's workspace: the account, its business engine (vertical
 * spec: record / catalog vocabulary and fields), its settings and this month's
 * usage. Loaded once by <MerchantGate> and shared through context; pages call
 * `refresh()` after changing settings.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { clearMerchantSession, merchantApi, merchantToken, saveMerchantProfile, type Workspace } from "@/services/api";

type WorkspaceState = {
  workspace: Workspace | null;
  error: string | null;
  refresh: () => Promise<Workspace | null>;
};

const WorkspaceContext = createContext<WorkspaceState>({
  workspace: null,
  error: null,
  refresh: async () => null,
});

export function WorkspaceProvider({ children, onUnauthorized }: { children: React.ReactNode; onUnauthorized: () => void }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadedAt = useRef(0);
  const pathname = usePathname();

  const refresh = useCallback(async () => {
    if (!merchantToken()) {
      onUnauthorized();
      return null;
    }
    try {
      const next = await merchantApi.workspace();
      loadedAt.current = Date.now();
      saveMerchantProfile(next.merchant);
      setWorkspace(next);
      setError(null);
      return next;
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 401 || status === 403) {
        clearMerchantSession();
        onUnauthorized();
      } else {
        setError(err instanceof Error ? err.message : "Could not load your workspace.");
      }
      return null;
    }
  }, [onUnauthorized]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Keep usage (minutes, chats) fresh while navigating, at most every 30 s.
  useEffect(() => {
    if (loadedAt.current && Date.now() - loadedAt.current > 30_000) void refresh();
  }, [pathname, refresh]);

  const value = useMemo(() => ({ workspace, error, refresh }), [workspace, error, refresh]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

/** The loaded workspace (inside <MerchantGate> it is never null). */
export function useWorkspace(): Workspace & { refresh: () => Promise<Workspace | null> } {
  const { workspace, refresh } = useContext(WorkspaceContext);
  if (!workspace) throw new Error("useWorkspace() outside a loaded <MerchantGate>");
  return { ...workspace, refresh };
}

/** Same, but null while loading (for the shell, which renders before the gate resolves). */
export function useWorkspaceMaybe(): Workspace | null {
  return useContext(WorkspaceContext).workspace;
}

export function useWorkspaceState(): WorkspaceState {
  return useContext(WorkspaceContext);
}
