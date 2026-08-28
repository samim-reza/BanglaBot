"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Building2, ClipboardList, LayoutDashboard, LogOut, PhoneCall, type LucideIcon } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { BanglaBotBrand, BanglaBotMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { adminToken, clearAdminSession } from "@/services/api";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: NavItem[] = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/merchants", label: "Merchants", icon: Building2 },
  { href: "/admin/orders", label: "Orders", icon: ClipboardList },
  { href: "/admin/calls", label: "Calls", icon: PhoneCall },
];

/**
 * Route guard for the admin console. `/admin/login` is public; every other
 * admin route needs a stored admin token, and a signed-in admin who visits the
 * login page is forwarded to the overview.
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
    return <div className="px-6 py-10 text-sm text-muted-foreground">Loading…</div>;
  }
  return <>{children}</>;
}

/** Header and section nav for the admin console. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useAppToast();
  const isLogin = pathname.startsWith("/admin/login");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <Link href="/admin" className="flex min-w-0 items-center gap-3">
            <BanglaBotMark compact />
            <BanglaBotBrand subtitle="Platform admin" />
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {!isLogin && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  clearAdminSession();
                  toast.success("Logged out.");
                  router.replace("/admin/login");
                }}
              >
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">Logout</span>
              </Button>
            )}
          </div>
        </div>
      </header>
      <div className="px-4 py-6 md:px-6">
        {isLogin ? (
          children
        ) : (
          <div className="flex flex-col gap-6 lg:flex-row">
            <aside className="lg:sticky lg:top-20 lg:h-fit lg:w-52 lg:shrink-0">
              <nav className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
                {NAV.map((item) => {
                  const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "inline-flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors lg:flex",
                        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                      )}
                    >
                      <item.icon className="h-4 w-4" />
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
            </aside>
            <div className="min-w-0 flex-1 space-y-6">{children}</div>
          </div>
        )}
      </div>
    </div>
  );
}
