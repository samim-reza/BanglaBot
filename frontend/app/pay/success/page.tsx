"use client";

/** Where Stripe sends a buyer after paying (`?reference=` may be present). */

import { useEffect, useState } from "react";
import Link from "next/link";
import { CircleCheck } from "lucide-react";

import { storedSignupReference } from "@/components/public/pay-view";
import { PublicNotice, PublicShell } from "@/components/public/public-shell";
import { Button } from "@/components/ui/button";

export default function PaySuccessPage() {
  const [reference, setReference] = useState("");
  useEffect(() => {
    setReference(storedSignupReference() || new URLSearchParams(window.location.search).get("reference") || "");
  }, []);
  return (
    <PublicShell>
      <PublicNotice icon={<CircleCheck className="h-6 w-6" aria-hidden />} title="Payment received" tone="success">
        <p>Thank you. A confirmation is on its way.</p>
        {reference && <p className="text-xs">Reference {reference}</p>}
        {reference && (
          <Button asChild>
            <Link href={`/signup/complete?reference=${encodeURIComponent(reference)}`}>Continue</Link>
          </Button>
        )}
      </PublicNotice>
    </PublicShell>
  );
}
