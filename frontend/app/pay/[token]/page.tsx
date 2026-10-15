"use client";

/** Public test pay page for a dummy payment link (`/pay/<token>`). */

import { useParams } from "next/navigation";

import { PayView } from "@/components/public/pay-view";
import { PublicShell } from "@/components/public/public-shell";

export default function PayPage() {
  const { token } = useParams<{ token: string }>();
  return (
    <PublicShell>
      <PayView token={decodeURIComponent(token ?? "")} />
    </PublicShell>
  );
}
