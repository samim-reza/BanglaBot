"use client";

import { useState } from "react";

import { useAdminMe } from "@/components/admin/shell/admin-me";
import { ConfirmDialog } from "@/components/admin/overlay";
import { LiveCallsTable } from "@/components/admin/live/live-calls-table";
import { useLiveCalls } from "@/components/admin/live/use-live-calls";
import { LoadingRows } from "@/components/admin/states";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, PageHeader } from "@/components/page-header";
import { isApiRequestError } from "@/services/api";
import { systemApi, type LiveCall } from "@/services/api/admin/system";

export default function AdminLiveCallsPage() {
  const { items, loaded, error, elapsed, reload } = useLiveCalls();
  const { can } = useAdminMe();
  const toast = useAppToast();
  const [target, setTarget] = useState<LiveCall | null>(null);

  const hangUp = async () => {
    if (!target) return;
    try {
      await systemApi.hangUp(target.call_log_id);
      toast.success("Call ended.");
    } catch (err) {
      if (!(isApiRequestError(err) && err.status === 404)) throw err;
      toast.success("That call had already ended.");
    }
    setTarget(null);
    void reload();
  };

  return (
    <>
      <PageHeader
        title="Live calls"
        subtitle={loaded ? `${items.length} in progress · updates every 3 s` : undefined}
      />
      <ApiError message={error} />
      {!loaded ? (
        <LoadingRows label="Loading live calls…" rows={3} />
      ) : items.length === 0 ? (
        error ? null : <EmptyState title="No calls in progress" />
      ) : (
        <LiveCallsTable items={items} elapsed={elapsed} canHangUp={can("hangUp")} onHangUp={setTarget} />
      )}
      <ConfirmDialog
        open={Boolean(target)}
        onClose={() => setTarget(null)}
        title="Hang up this call?"
        confirmLabel="Hang up"
        busyLabel="Hanging up…"
        tone="danger"
        onConfirm={hangUp}
      >
        <p>
          {target?.business || "This account"} · <span className="font-mono">{target?.caller || "caller"}</span>
        </p>
        <p>The caller is disconnected immediately.</p>
      </ConfirmDialog>
    </>
  );
}
