"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { WorkspaceProvider, useWorkspaceState } from "@/lib/workspace";

function Ready({ children }: { children: React.ReactNode }) {
  const { workspace, error, refresh } = useWorkspaceState();
  if (error) {
    return (
      <div className="px-6 py-10 text-sm">
        <p className="text-destructive">{error}</p>
        <Button className="mt-3" size="sm" variant="outline" onClick={() => void refresh()}>
          Retry
        </Button>
      </div>
    );
  }
  if (!workspace) return <div className="px-6 py-10 text-sm text-muted-foreground">Loading…</div>;
  return <>{children}</>;
}

/**
 * Route guard + data root for the account portal. Pages render once the stored
 * token has been validated by loading the workspace; a missing or dead token
 * sends the user to `/login`.
 */
export function MerchantGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const onUnauthorized = useCallback(() => router.replace("/login"), [router]);
  return (
    <WorkspaceProvider onUnauthorized={onUnauthorized}>
      <Ready>{children}</Ready>
    </WorkspaceProvider>
  );
}
