"use client";

/** The add-on shop moved into Plan & add-ons; old links (and their #add-on anchors) land there. */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AddonsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace(`/plan${window.location.hash}`);
  }, [router]);
  return <div className="px-2 py-6 text-sm text-muted-foreground">Opening Plan &amp; add-ons…</div>;
}
