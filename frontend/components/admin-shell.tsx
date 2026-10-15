"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";

import { AccountChip } from "@/components/admin/shell/account-chip";
import { AdminMeProvider } from "@/components/admin/shell/admin-me";
import { NavList, WebsiteLink } from "@/components/admin/shell/nav";
import { useNavBadges } from "@/components/admin/shell/use-nav-badges";
import { useAppToast } from "@/components/app-toast";
import { BanglaBotBrand, BanglaBotMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { clearAdminSession } from "@/services/api";

export { AdminGate } from "@/components/admin/shell/admin-gate";
export { INQUIRIES_CHANGED_EVENT } from "@/components/admin/shell/use-nav-badges";

/** Header, sidebar and mobile drawer for the platform admin console. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname.startsWith("/admin/login");
  return (
    <AdminMeProvider enabled={!isLogin}>
      <ShellFrame pathname={pathname} isLogin={isLogin}>
        {children}
      </ShellFrame>
    </AdminMeProvider>
  );
}

function ShellFrame({ pathname, isLogin, children }: { pathname: string; isLogin: boolean; children: React.ReactNode }) {
  const router = useRouter();
  const toast = useAppToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const counts = useNavBadges(!isLogin, pathname);

  useEffect(() => setMenuOpen(false), [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setMenuOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const logout = () => {
    clearAdminSession();
    toast.success("Signed out of the admin console.");
    router.replace("/admin/login");
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#admin-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-card">
        <div className="flex h-[57px] items-center justify-between gap-3 px-4">
          <div className="flex min-w-0 items-center gap-2">
            {!isLogin && (
              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
                aria-label="Open navigation"
                aria-expanded={menuOpen}
                aria-controls="admin-mobile-nav"
                onClick={() => setMenuOpen(true)}
              >
                <Menu className="h-4 w-4" />
              </button>
            )}
            <Link href={isLogin ? "/" : "/admin"} className="flex min-w-0 items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <BanglaBotMark compact />
              <BanglaBotBrand subtitle="Platform admin" />
            </Link>
          </div>
          <div className="flex items-center gap-2">
            {!isLogin && <AccountChip />}
            <ThemeToggle />
            {!isLogin && (
              <Button variant="ghost" size="sm" onClick={logout} aria-label="Sign out">
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            )}
          </div>
        </div>
      </header>

      {isLogin ? (
        <main id="admin-main" className="px-4 py-6 md:px-6">
          {children}
        </main>
      ) : (
        <div className="flex min-h-[calc(100vh-57px)]">
          <aside className="hidden w-60 shrink-0 border-r border-border bg-card lg:block">
            <div className="sticky top-[57px] flex h-[calc(100vh-57px)] flex-col overflow-y-auto p-3">
              <NavList pathname={pathname} counts={counts} />
              <div className="mt-auto border-t border-border pt-3">
                <WebsiteLink />
              </div>
            </div>
          </aside>
          <main id="admin-main" className="min-w-0 flex-1 px-4 py-6 md:px-6">
            <div className="mx-auto max-w-7xl space-y-6">{children}</div>
          </main>
        </div>
      )}

      {menuOpen && !isLogin && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" className="absolute inset-0 bg-black/40" aria-label="Close navigation" tabIndex={-1} onClick={() => setMenuOpen(false)} />
          <aside
            id="admin-mobile-nav"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-card shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">Platform admin</span>
              <button
                type="button"
                autoFocus
                className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close navigation"
                onClick={() => setMenuOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-1 flex-col overflow-y-auto p-3">
              <NavList pathname={pathname} counts={counts} onNavigate={() => setMenuOpen(false)} />
              <div className="mt-auto border-t border-border pt-3">
                <WebsiteLink onNavigate={() => setMenuOpen(false)} />
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
