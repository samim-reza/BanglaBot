"use client";

/** Return page after signup checkout (`?reference=`): polls the signup's status. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { CircleX } from "lucide-react";

import { LEGACY_SIGNUP_REFERENCE_KEY, SIGNUP_REFERENCE_KEY } from "@/components/public/pay-view";
import { PublicNotice, PublicShell } from "@/components/public/public-shell";
import { SignupStatusNotice } from "@/components/public/signup-status";
import { Button } from "@/components/ui/button";
import { formatApiError, signupApi, type SignupStatus } from "@/services/api";

const POLL_MS = 4000;
const MAX_POLLS = 45;

export default function SignupCompletePage() {
  const [reference, setReference] = useState<string | null>(null);
  const [status, setStatus] = useState<SignupStatus | null>(null);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReference(new URLSearchParams(window.location.search).get("reference") ?? "");
  }, []);

  useEffect(() => {
    if (!reference) return;
    let polls = 0;
    let timer = 0;
    let stopped = false;
    const check = async () => {
      try {
        const next = await signupApi.status(reference);
        if (stopped) return;
        setStatus(next.status);
        setVerified(next.email_verified);
        setError(null);
        if (next.status === "approved" || next.status === "rejected") {
          try {
            window.sessionStorage.removeItem(SIGNUP_REFERENCE_KEY);
            window.sessionStorage.removeItem(LEGACY_SIGNUP_REFERENCE_KEY);
          } catch {
            // storage blocked: nothing to clean up
          }
        }
        if (next.status === "pending_payment" && ++polls < MAX_POLLS) timer = window.setTimeout(() => void check(), POLL_MS);
      } catch (err) {
        if (!stopped) setError(formatApiError(err, "Could not check your signup."));
      }
    };
    void check();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [reference]);

  return (
    <PublicShell>
      {reference === "" || error ? (
        <PublicNotice icon={<CircleX className="h-6 w-6" aria-hidden />} title="Signup not found" tone="error">
          <p>{error ?? "This link is missing its reference."}</p>
          <Button asChild variant="outline">
            <Link href="/get-started">Start again</Link>
          </Button>
        </PublicNotice>
      ) : (
        <SignupStatusNotice status={status} emailVerified={verified} />
      )}
    </PublicShell>
  );
}
