"use client";

/** The email verification link (`?token=`). */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CircleCheck, CircleX, LoaderCircle } from "lucide-react";

import { PublicNotice, PublicShell } from "@/components/public/public-shell";
import { Button } from "@/components/ui/button";
import { formatApiError, signupApi, type SignupStatus } from "@/services/api";

const NEXT: Record<SignupStatus, string> = {
  pending_payment: "Finish your payment to continue.",
  awaiting_approval: "We'll email you when your account is ready.",
  approved: "Your account is ready.",
  rejected: "This signup wasn't approved — contact us.",
};

export default function SignupVerifyPage() {
  const [status, setStatus] = useState<SignupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    if (!token) {
      setError("This link is missing its code.");
      return;
    }
    signupApi
      .verifyEmail(token)
      .then((result) => {
        if (!result.verified) setError("This link has expired.");
        else setStatus(result.status);
      })
      .catch((err) => setError(formatApiError(err, "This link is invalid or has expired.")));
  }, []);

  return (
    <PublicShell>
      {error ? (
        <PublicNotice icon={<CircleX className="h-6 w-6" aria-hidden />} title="Couldn't verify" tone="error">
          <p>{error}</p>
        </PublicNotice>
      ) : status ? (
        <PublicNotice icon={<CircleCheck className="h-6 w-6" aria-hidden />} title="Email verified" tone="success">
          <p>{NEXT[status] ?? ""}</p>
          {status === "approved" && (
            <Button asChild>
              <Link href="/login">Sign in</Link>
            </Button>
          )}
        </PublicNotice>
      ) : (
        <PublicNotice icon={<LoaderCircle className="h-6 w-6 animate-spin" aria-hidden />} title="Verifying your email" />
      )}
    </PublicShell>
  );
}
