"use client";

/** After signup checkout: where the account stands (paid? approved? email verified?). */

import Link from "next/link";
import { CircleCheck, CircleX, Clock, LoaderCircle, MailCheck } from "lucide-react";

import { PublicNotice } from "@/components/public/public-shell";
import { Button } from "@/components/ui/button";
import type { SignupStatus } from "@/services/api";

export function SignupStatusNotice({ status, emailVerified }: { status: SignupStatus | null; emailVerified: boolean }) {
  if (status === null || status === "pending_payment") {
    return (
      <PublicNotice icon={<LoaderCircle className="h-6 w-6 animate-spin" aria-hidden />} title="Waiting for your payment">
        <p>This page updates by itself.</p>
      </PublicNotice>
    );
  }
  if (status === "rejected") {
    return (
      <PublicNotice icon={<CircleX className="h-6 w-6" aria-hidden />} title="Signup not approved" tone="error">
        <p>Questions? We&apos;re happy to help.</p>
        <Button asChild variant="outline">
          <Link href="/contact">Contact us</Link>
        </Button>
      </PublicNotice>
    );
  }
  const verify = !emailVerified && (
    <p className="flex items-center justify-center gap-1.5">
      <MailCheck className="h-4 w-4" aria-hidden />
      Check your inbox to verify your email.
    </p>
  );
  if (status === "awaiting_approval") {
    return (
      <PublicNotice icon={<Clock className="h-6 w-6" aria-hidden />} title="Paid — setting you up">
        <p>We&apos;ll email you when your account is ready.</p>
        {verify}
      </PublicNotice>
    );
  }
  return (
    <PublicNotice icon={<CircleCheck className="h-6 w-6" aria-hidden />} title="You're all set" tone="success">
      {verify}
      <Button asChild>
        <Link href="/login">Sign in</Link>
      </Button>
    </PublicNotice>
  );
}
