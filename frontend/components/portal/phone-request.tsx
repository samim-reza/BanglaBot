"use client";

/** Owners can't buy phone numbers: they request one and our team assigns it (Dashboard → Finish setup, Channels → Phone line). */

import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { formatApiError, phoneLineApi } from "@/services/api";

/** Whether a number was requested, and a button to request one (only loaded while there's no number). */
export function usePhoneRequest(active: boolean): { requested: boolean; action: React.ReactNode } {
  const toast = useAppToast();
  const [requested, setRequested] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    phoneLineApi
      .get()
      .then((view) => {
        if (!cancelled) setRequested(view.request?.status === "pending");
      })
      .catch(() => undefined); // the button still works
    return () => {
      cancelled = true;
    };
  }, [active]);

  const request = async () => {
    setBusy(true);
    try {
      const view = await phoneLineApi.request();
      setRequested(view.request?.status === "pending");
      toast.success("Number requested.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not send the request."));
    } finally {
      setBusy(false);
    }
  };

  const action = requested ? (
    <span className="shrink-0 rounded-full bg-accent px-2.5 py-0.5 text-[12px] font-semibold text-accent-foreground">Requested</span>
  ) : (
    <Button type="button" size="sm" variant="outline" className="shrink-0" disabled={busy} onClick={() => void request()}>
      {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
      Request
    </Button>
  );
  return { requested, action };
}
