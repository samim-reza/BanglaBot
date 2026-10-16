"use client";

/** The test pay page behind a dummy payment link: what is owed, and "Pay (test)". */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CircleCheck, CircleX, CreditCard, LoaderCircle } from "lucide-react";

import { PublicNotice } from "@/components/public/public-shell";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { money } from "@/lib/vertical";
import { formatApiError, isApiRequestError, merchantToken, payApi, type PayPage } from "@/services/api";

/** Set by the signup wizard before checkout, so a paid signup can continue to its status page. */
export const SIGNUP_REFERENCE_KEY = "callisa_signup_reference";
/** Pre-rename key, still read so a checkout started before the Callisa rename can continue. */
export const LEGACY_SIGNUP_REFERENCE_KEY = "banglabot_signup_reference";

export function storedSignupReference(): string {
  try {
    const store = window.sessionStorage;
    return store.getItem(SIGNUP_REFERENCE_KEY) ?? store.getItem(LEGACY_SIGNUP_REFERENCE_KEY) ?? "";
  } catch {
    return "";
  }
}

function NextStep({ page }: { page: PayPage }) {
  if (page.kind !== "subscription") return <p>You can close this page.</p>;
  const reference = storedSignupReference();
  const href = reference ? `/signup/complete?reference=${encodeURIComponent(reference)}` : merchantToken() ? "/plan?reference=paid" : "/login";
  return (
    <Button asChild>
      <Link href={href}>Continue</Link>
    </Button>
  );
}

export function PayView({ token }: { token: string }) {
  const [page, setPage] = useState<PayPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPage(await payApi.view(token));
      setError(null);
    } catch (err) {
      setError(isApiRequestError(err) && err.status === 404 ? "This payment link is invalid or has expired." : formatApiError(err, "Could not open this payment link."));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const pay = async () => {
    setPaying(true);
    setPayError(null);
    try {
      setPage(await payApi.complete(token));
    } catch (err) {
      setPayError(isApiRequestError(err) && err.status === 429 ? "Too many tries — wait a minute." : formatApiError(err, "Payment failed."));
      void load();
    } finally {
      setPaying(false);
    }
  };

  if (error) {
    return (
      <PublicNotice icon={<CircleX className="h-6 w-6" aria-hidden />} title="Link not valid" tone="error">
        <p>{error}</p>
        <p>Ask the business for a new link.</p>
      </PublicNotice>
    );
  }
  if (!page) return <div className="h-64 animate-pulse rounded-lg bg-secondary" aria-busy="true" aria-label="Loading" />;

  const amount = money(page.amount, page.currency);
  if (page.status === "paid") {
    return (
      <PublicNotice icon={<CircleCheck className="h-6 w-6" aria-hidden />} title="Paid" tone="success">
        <p>
          {amount} to {page.business || "the business"}
          {page.paid_at ? ` · ${formatDateTime(page.paid_at)}` : ""}
        </p>
        <p className="text-xs">Reference {page.reference}</p>
        <NextStep page={page} />
      </PublicNotice>
    );
  }
  if (!page.can_complete) {
    return (
      <PublicNotice icon={<CircleX className="h-6 w-6" aria-hidden />} title={page.status === "expired" ? "Link expired" : "Can't pay here"} tone="error">
        <p>{page.status === "expired" ? "Ask the business for a new link." : `This payment is ${page.status}.`}</p>
      </PublicNotice>
    );
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-6">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-accent text-accent-foreground">
          <CreditCard className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate font-semibold">{page.business || "Payment"}</p>
          {page.description && <p className="truncate text-sm text-muted-foreground">{page.description}</p>}
        </div>
      </div>
      <p className="text-3xl font-bold tabular-nums">{amount}</p>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-muted-foreground">Reference</dt>
        <dd className="text-right font-medium">{page.reference}</dd>
        {page.expires_at && (
          <>
            <dt className="text-muted-foreground">Pay by</dt>
            <dd className="text-right">{formatDateTime(page.expires_at)}</dd>
          </>
        )}
      </dl>
      {payError && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {payError}
        </p>
      )}
      <Button type="button" className="w-full" disabled={paying} onClick={() => void pay()}>
        {paying && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
        Pay (test)
      </Button>
      <p className="text-center text-xs text-muted-foreground">Test mode — no money moves.</p>
    </div>
  );
}
