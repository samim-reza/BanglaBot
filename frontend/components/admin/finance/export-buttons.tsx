"use client";

import { useState } from "react";
import { Download } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { formatApiError } from "@/services/api";
import { financeApi } from "@/services/api/admin/finance";

/** Daily / per-account CSV for the month (fetched with the session, then saved). */
export function ExportButtons({ month }: { month: string }) {
  const toast = useAppToast();
  const [busy, setBusy] = useState<"daily" | "accounts" | null>(null);

  const download = async (kind: "daily" | "accounts") => {
    setBusy(kind);
    try {
      const { blob, filename } = await financeApi.exportCsv(kind, month);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      toast.error(formatApiError(err, "Export failed."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => void download("daily")} disabled={busy !== null} title="One row per day">
        <Download className="h-3.5 w-3.5" />
        {busy === "daily" ? "Exporting…" : "Daily CSV"}
      </Button>
      <Button variant="outline" size="sm" onClick={() => void download("accounts")} disabled={busy !== null} title="One row per account">
        <Download className="h-3.5 w-3.5" />
        {busy === "accounts" ? "Exporting…" : "Accounts CSV"}
      </Button>
    </>
  );
}
