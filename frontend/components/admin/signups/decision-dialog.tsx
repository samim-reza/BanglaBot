"use client";

import { useEffect, useId, useState } from "react";

import { DialogError, Overlay } from "@/components/admin/overlay";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { formatApiError } from "@/services/api";
import { signupsApi, type Signup } from "@/services/api/admin/signups";

/** Approve (optionally marking it paid offline) or reject a signup, with a note. */
export function DecisionDialog({
  signup,
  decision,
  onClose,
  onDone,
}: {
  signup: Signup | null;
  decision: "approve" | "reject";
  onClose: () => void;
  onDone: (updated: Signup) => void;
}) {
  const [note, setNote] = useState("");
  const [markPaid, setMarkPaid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const noteId = useId();

  useEffect(() => {
    if (signup) {
      setNote("");
      setMarkPaid(false);
      setError(null);
    }
  }, [signup]);

  const unpaid = signup?.status === "pending_payment";
  const submit = async () => {
    if (!signup) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await signupsApi.decide(signup.merchant_id, decision, { note: note.trim(), mark_paid: decision === "approve" && markPaid }));
    } catch (err) {
      setError(formatApiError(err, "Could not save the decision."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Overlay
      open={Boolean(signup)}
      onClose={onClose}
      busy={busy}
      size="sm"
      title={decision === "approve" ? "Approve signup?" : "Reject signup?"}
      description={signup ? `${signup.business_name} · ${signup.email}` : undefined}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant={decision === "reject" ? "destructive" : "default"} onClick={() => void submit()} disabled={busy}>
            {busy ? "Saving…" : decision === "approve" ? "Approve" : "Reject"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {decision === "approve" && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]" checked={markPaid} onChange={(e) => setMarkPaid(e.target.checked)} />
            <span>
              <span className="font-medium">Mark as paid</span>
              <span className="block text-xs text-muted-foreground">{unpaid ? "Paid offline — activates the subscription." : "Records an offline payment."}</span>
            </span>
          </label>
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor={noteId} className="text-[13.5px] font-semibold text-muted-foreground">
            Note
          </label>
          <Textarea id={noteId} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Optional" />
        </div>
        <DialogError message={error} />
      </div>
    </Overlay>
  );
}
