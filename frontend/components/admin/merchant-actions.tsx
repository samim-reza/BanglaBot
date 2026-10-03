"use client";

import { useAppToast } from "@/components/app-toast";
import { withBasePath } from "@/lib/paths";
import { adminApi, saveMerchantSession, type Merchant } from "@/services/api";

import { ConfirmDialog } from "./overlay";

/**
 * "Open portal": swaps this browser's admin session for a 2-hour owner session
 * of the account and lands on its dashboard. Confirmed first, because it signs
 * the admin out of the console in this browser.
 */
export function OpenPortalDialog({ merchant, onClose }: { merchant: Merchant | null; onClose: () => void }) {
  return (
    <ConfirmDialog
      open={Boolean(merchant)}
      onClose={onClose}
      title="Open this account's portal?"
      confirmLabel="Sign out & open portal"
      busyLabel="Opening portal…"
      onConfirm={async () => {
        if (!merchant) return;
        const session = await adminApi.impersonate(merchant.id);
        saveMerchantSession(session.token, session.merchant);
        window.location.assign(withBasePath("/dashboard"));
        // Keep the dialog busy while the browser navigates away.
        await new Promise(() => undefined);
      }}
    >
      <p>
        You&apos;ll be signed in as the owner of <strong className="text-foreground">{merchant?.business_name}</strong>{" "}
        <span className="font-mono text-xs">(@{merchant?.username})</span> for up to 2 hours, to set up or troubleshoot their workspace.
      </p>
      <p>
        <strong className="text-foreground">This signs you out of the admin console in this browser.</strong> To return, sign in
        to the admin console again. Use a private window if you want to keep both open.
      </p>
      <p>Anything you change in the portal is saved to the live account.</p>
    </ConfirmDialog>
  );
}

/** Permanent delete, confirmed by typing the username. The API refuses (409) while a call is live. */
export function DeleteMerchantDialog({
  merchant,
  onClose,
  onDeleted,
}: {
  merchant: Merchant | null;
  onClose: () => void;
  onDeleted: (merchant: Merchant) => void;
}) {
  const toast = useAppToast();
  return (
    <ConfirmDialog
      open={Boolean(merchant)}
      onClose={onClose}
      title="Delete account?"
      tone="danger"
      confirmLabel="Delete account"
      busyLabel="Deleting…"
      confirmText={merchant?.username ?? ""}
      onConfirm={async () => {
        if (!merchant) return;
        await adminApi.deleteMerchant(merchant.id);
        toast.success(`"${merchant.business_name}" deleted.`);
        onDeleted(merchant);
      }}
    >
      <p>
        This permanently deletes <strong className="text-foreground">{merchant?.business_name}</strong> with all of its records,
        catalog items and call &amp; chat history. It can&apos;t be undone.
      </p>
      {merchant?.inbound_number && (
        <p>
          Its inbound number <span className="font-mono text-foreground">{merchant.inbound_number}</span> will stop being answered.
        </p>
      )}
    </ConfirmDialog>
  );
}
