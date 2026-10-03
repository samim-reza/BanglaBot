"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { BanglaBotMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { SITE_NAV, TRIAL_HREF } from "@/lib/site-content";
import { cn } from "@/lib/utils";
import { adminToken, merchantToken } from "@/services/api";

type Session = { href: string; label: string } | null;

export function SiteHeader() {
  const pathname = usePathname();
  const menuId = useId();
  // The menu remembers the path it was opened on, so any navigation closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (value: boolean) => setOpenOn(value ? pathname : null);
  const [session, setSession] = useState<Session>(null);

  // Tokens live in localStorage, so the signed-in state is only known after mount.
  useEffect(() => {
    if (merchantToken()) setSession({ href: "/dashboard", label: "Open dashboard" });
    else if (adminToken()) setSession({ href: "/admin", label: "Open admin" });
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenOn(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const account = session ?? { href: "/login", label: "Sign in" };

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`${BRAND.name} home`}
        >
          <BanglaBotMark compact />
          <span className="text-lg font-bold tracking-tight text-primary-dark">{BRAND.name}</span>
        </Link>

        <nav aria-label="Main" className="ml-6 hidden items-center gap-1 lg:flex">
          {SITE_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item.href) ? "page" : undefined}
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive(item.href) && "text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <Button asChild variant="ghost" className="hidden sm:inline-flex">
            <Link href={account.href}>{account.label}</Link>
          </Button>
          <Button asChild className="hidden sm:inline-flex">
            <Link href={TRIAL_HREF}>Start free trial</Link>
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 lg:hidden"
            aria-expanded={open}
            aria-controls={menuId}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen(!open)}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div id={menuId} hidden={!open} className="border-t border-border bg-background lg:hidden">
        <nav aria-label="Mobile" className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-4 sm:px-6">
          {SITE_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item.href) ? "page" : undefined}
              onClick={() => setOpenOn(null)}
              className={cn(
                "rounded-md px-3 py-2.5 text-base font-medium text-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive(item.href) && "bg-accent text-accent-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-4">
            <Button asChild variant="outline">
              <Link href={account.href} onClick={() => setOpenOn(null)}>
                {account.label}
              </Link>
            </Button>
            <Button asChild>
              <Link href={TRIAL_HREF} onClick={() => setOpenOn(null)}>
                Start free trial
              </Link>
            </Button>
          </div>
        </nav>
      </div>
    </header>
  );
}
