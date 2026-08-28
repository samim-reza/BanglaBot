"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { clearMerchantSession, merchantApi, merchantToken, saveMerchantProfile } from "@/services/api";

/**
 * Route guard for the merchant workspace. Pages render only once a stored
 * merchant token has been validated against `/api/auth/me`; a missing or dead
 * token sends the user to `/login`.
 */
export function MerchantGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [readyPath, setReadyPath] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setReadyPath(null);
    if (!merchantToken()) {
      router.replace("/login");
      return;
    }
    merchantApi
      .me()
      .then((merchant) => {
        saveMerchantProfile(merchant);
        if (!cancelled) setReadyPath(pathname);
      })
      .catch(() => {
        clearMerchantSession();
        if (!cancelled) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (readyPath !== pathname) {
    return <div className="px-6 py-10 text-sm text-muted-foreground">Loading…</div>;
  }
  return <>{children}</>;
}
