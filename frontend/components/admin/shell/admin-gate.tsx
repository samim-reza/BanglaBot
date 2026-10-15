"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { adminToken } from "@/services/api";

/**
 * Route guard for the admin console. `/admin/login` is public; every other
 * admin route needs a stored admin token, and a signed-in admin who visits the
 * login page is forwarded to the dashboard.
 */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [readyPath, setReadyPath] = useState<string | null>(null);
  const isLogin = pathname.startsWith("/admin/login");

  useEffect(() => {
    setReadyPath(null);
    const token = adminToken();
    if (isLogin) {
      if (token) {
        router.replace("/admin");
        return;
      }
      setReadyPath(pathname);
      return;
    }
    if (!token) {
      router.replace("/admin/login");
      return;
    }
    setReadyPath(pathname);
  }, [isLogin, pathname, router]);

  if (readyPath !== pathname) {
    return (
      <div className="px-1 py-10 text-sm text-muted-foreground" role="status">
        Loading…
      </div>
    );
  }
  return <>{children}</>;
}
