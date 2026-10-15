/** Where Stripe sends a buyer who backed out of checkout. */

import Link from "next/link";
import { CircleX } from "lucide-react";

import { PublicNotice, PublicShell } from "@/components/public/public-shell";
import { Button } from "@/components/ui/button";

export default function PayCancelledPage() {
  return (
    <PublicShell>
      <PublicNotice icon={<CircleX className="h-6 w-6" aria-hidden />} title="Payment cancelled" tone="error">
        <p>Nothing was charged. Use the link again when you&apos;re ready.</p>
        <Button asChild variant="outline">
          <Link href="/">Back home</Link>
        </Button>
      </PublicNotice>
    </PublicShell>
  );
}
