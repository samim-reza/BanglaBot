"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Building2,
  ClipboardList,
  ExternalLink,
  Inbox,
  LayoutDashboard,
  LogOut,
  Menu,
  MessagesSquare,
  X,
  type LucideIcon,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { BanglaBotBrand, BanglaBotMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { adminApi, adminToken, clearAdminSession } from "@/services/api";

type NavItem = { href: string; label: string; icon: LucideIcon; badge?: "inquiries" };

const NAV: NavItem[] = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/merchants", label: "Accounts", icon: Building2 },
  { href: "/admin/orders", label: "Records", icon: ClipboardList },
  { href: "/admin/calls", label: "Calls & chats", icon: MessagesSquare },
  { href: "/admin/inquiries", label: "Sales inquiries", icon: Inbox, badge: "inquiries" },
];

/** Fired by screens that change inquiry statuses so the nav count refreshes. */
export const INQUIRIES_CHANGED_EVENT = "admin:inquiries-changed";

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
    return (
      <div className="px-1 py-10 text-sm text-muted-foreground" role="status">
        Loading…
      </div>
    );
  }
  return <>{children}</>;
}

/** Count of "new" sales inquiries for the nav badge; refreshed on navigation and on change events. */
function useNewInquiries(enabled: boolean, pathname: string): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled || !adminToken()) return;
    let cancelled = false;
    const load = () =>
      adminApi
        .inquiries({ status: "new", page_size: 1 })
        .then((page) => !cancelled && setCount(page.total))
        .catch(() => undefined);
    void load();
    window.addEventListener(INQUIRIES_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(INQUIRIES_CHANGED_EVENT, load);
    };
  }, [enabled, pathname]);
  return enabled ? count : 0;
}

function NavList({ pathname, newInquiries, onNavigate }: { pathname: string; newInquiries: number; onNavigate?: () => void }) {
  return (
    <nav aria-label="Admin console" className="flex flex-col gap-1">
      {NAV.map((item) => {
        const active = item.href === "/admin" ? pathname === "/admin" : pathname === item.href || pathname.startsWith(`${item.href}/`);
        const count = item.badge === "inquiries" ? newInquiries : 0;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="flex-1">{item.label}</span>
            {count > 0 && (
              <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-bold leading-none text-primary-foreground">
                {count > 99 ? "99+" : count}
                <span className="sr-only"> new</span>
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function WebsiteLink({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link
      href="/"
      target="_blank"
      rel="noopener"
      onClick={onNavigate}
      className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ExternalLink className="h-4 w-4 shrink-0" aria-hidden="true" />
      Public website
      <span className="sr-only">(opens in a new tab)</span>
    </Link>
  );
}

/** Header, sidebar and mobile drawer for the platform admin console. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useAppToast();
  const isLogin = pathname.startsWith("/admin/login");
  const [menuOpen, setMenuOpen] = useState(false);
  const newInquiries = useNewInquiries(!isLogin, pathname);

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
              <p className="mb-2 px-3 text-[12px] font-semibold text-muted-foreground">Console</p>
              <NavList pathname={pathname} newInquiries={newInquiries} />
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
              <NavList pathname={pathname} newInquiries={newInquiries} onNavigate={() => setMenuOpen(false)} />
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
