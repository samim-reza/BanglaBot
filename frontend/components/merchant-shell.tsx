"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ClipboardList, LayoutDashboard, LogOut, Menu, PlusCircle, Settings, UserRound, X, type LucideIcon } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { BanglaBotBrand, BanglaBotMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { clearMerchantSession, getMerchantSession, type Merchant } from "@/services/api";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/orders", label: "Orders", icon: ClipboardList },
  { href: "/orders/new", label: "New order", icon: PlusCircle },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  // Only the longest matching href is active, so /orders never lights up with /orders/new.
  const matches = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const activeHref = NAV.reduce<string | null>(
    (best, item) => (matches(item.href) && (best === null || item.href.length > best.length) ? item.href : best),
    null,
  );
  return (
    <nav className="flex flex-col gap-1">
      {NAV.map((item) => {
        const active = item.href === activeHref;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition",
              active ? "bg-accent font-medium text-accent-foreground" : "font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function LogoutButton({ merchant }: { merchant: Merchant | null }) {
  const router = useRouter();
  const toast = useAppToast();
  return (
    <div className="flex items-center gap-1 md:gap-2">
      {merchant && (
        <Link href="/settings" className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted-foreground hover:text-foreground sm:inline-flex">
          <UserRound className="h-4 w-4" />
          <span className="max-w-40 truncate">{merchant.business_name}</span>
        </Link>
      )}
      <Button
        variant="ghost"
        size="sm"
        aria-label="Logout"
        onClick={() => {
          clearMerchantSession();
          toast.success("Logged out.");
          router.replace("/login");
        }}
      >
        <LogOut className="h-4 w-4" />
        <span className="hidden sm:inline">Logout</span>
      </Button>
    </div>
  );
}

/** Header, sidebar and mobile drawer for every signed-in merchant page. */
export function MerchantShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [merchant, setMerchant] = useState<Merchant | null>(null);

  useEffect(() => {
    setOpen(false);
    setMerchant(getMerchantSession().merchant);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card md:hidden"
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </button>
            <Link href="/dashboard" className="flex min-w-0 items-center gap-3">
              <BanglaBotMark compact />
              <BanglaBotBrand subtitle="Merchant workspace" />
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <LogoutButton merchant={merchant} />
          </div>
        </div>
      </header>
      <div className="flex min-h-[calc(100vh-57px)]">
        <aside className="hidden w-56 shrink-0 border-r border-border bg-card md:block">
          <div className="sticky top-[57px] h-[calc(100vh-57px)] overflow-y-auto p-3">
            <p className="mb-2 px-3 text-[12px] font-semibold text-muted-foreground">Workspace</p>
            <NavList />
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 md:px-6">{children}</main>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button type="button" className="absolute inset-0 bg-foreground/30" aria-label="Close navigation" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">Navigation</span>
              <button
                type="button"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-secondary"
                aria-label="Close navigation"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <NavList onNavigate={() => setOpen(false)} />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
