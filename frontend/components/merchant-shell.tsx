"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Building2,
  CalendarCheck,
  CalendarClock,
  CirclePlus,
  ClipboardList,
  Contact,
  LayoutDashboard,
  LogOut,
  Menu,
  MessagesSquare,
  Package,
  Puzzle,
  Radio,
  Settings,
  ShoppingBag,
  Stethoscope,
  UserRound,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { BanglaBotBrand, BanglaBotMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { clearMerchantSession, type Usage, type VerticalSpec } from "@/services/api";

type NavItem = { href: string; label: string; icon: LucideIcon };

const RECORD_ICONS: Record<string, LucideIcon> = {
  ecommerce: ShoppingBag,
  clinic: CalendarCheck,
  real_estate: Contact,
  home_service: CalendarClock,
};

const CATALOG_ICONS: Record<string, LucideIcon> = {
  clinic: Stethoscope,
  real_estate: Building2,
  home_service: Wrench,
};

function navFor(vertical: VerticalSpec): NavItem[] {
  const items: NavItem[] = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/orders", label: t(vertical.record_label_plural, "Records"), icon: RECORD_ICONS[vertical.key] ?? ClipboardList },
    { href: "/orders/new", label: `New ${t(vertical.record_label, "record").toLowerCase()}`, icon: CirclePlus },
  ];
  if (vertical.catalog_kind) {
    items.push({ href: "/catalog", label: t(vertical.catalog_label_plural, "Catalog"), icon: CATALOG_ICONS[vertical.key] ?? Package });
  }
  items.push(
    { href: "/calls", label: "Calls & chats", icon: MessagesSquare },
    { href: "/channels", label: "Channels", icon: Radio },
    { href: "/addons", label: "Add-ons", icon: Puzzle },
    { href: "/settings", label: "Settings", icon: Settings },
  );
  return items;
}

function NavList({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  // Only the longest matching href is active, so /orders never lights up with /orders/new.
  const matches = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const activeHref = items.reduce<string | null>(
    (best, item) => (matches(item.href) && (best === null || item.href.length > best.length) ? item.href : best),
    null,
  );
  return (
    <nav aria-label="Account" className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active = item.href === activeHref;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/** Minutes allowed this month (plan + add-ons); null or 0 when there is no cap. */
function minuteLimit(usage: Usage): number | null {
  return usage.limits ? usage.limits.minutes : usage.plan.included_minutes;
}

/** Share of the month's minute allowance used (null when there is no cap). */
export function usageShare(usage: Usage): number | null {
  const limit = minuteLimit(usage);
  if (!limit) return null;
  return Math.min(1, Math.max(0, usage.minutes / limit));
}

/** Thin "used of allowed" meter; turns amber past 80% and red past 100%. */
function ShareBar({ used, limit, label, className }: { used: number; limit: number; label: string; className?: string }) {
  const share = Math.min(1, Math.max(0, used / limit));
  const tone = used > limit ? "bg-destructive" : share >= 0.8 ? "bg-amber-500" : "bg-primary";
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={limit}
      aria-valuenow={Math.min(used, limit)}
      aria-valuetext={`${used} of ${limit}`}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-secondary", className)}
    >
      <div className={cn("h-full rounded-full transition-[width]", tone)} style={{ width: `${Math.max(share * 100, share > 0 ? 3 : 0)}%` }} />
    </div>
  );
}

/** Minutes used of this month's allowance (nothing when there is no cap). */
export function UsageBar({ usage, className, label = "Call minutes used this month" }: { usage: Usage; className?: string; label?: string }) {
  const limit = minuteLimit(usage);
  if (!limit) return null;
  return <ShareBar used={usage.minutes} limit={limit} label={label} className={className} />;
}

function minutes(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { merchant, vertical, usage, entitlements } = useWorkspace();
  const items = navFor(vertical);
  // Voice plans track minutes; the chat plan tracks chats.
  const voice = entitlements.channels.includes("voice");
  const used = voice ? usage.minutes : usage.chats;
  const limit = (voice ? usage.limits?.minutes : usage.limits?.chats) ?? null;
  const unit = voice ? "min" : "chats";
  return (
    <div className="flex h-full flex-col gap-4">
      <div className="rounded-lg border border-border bg-surface px-3 py-3">
        <p className="truncate text-sm font-semibold" title={merchant.business_name}>
          {merchant.business_name}
        </p>
        <span className="mt-1.5 inline-flex max-w-full items-center rounded-full bg-accent px-2 py-0.5 text-[11.5px] font-semibold text-accent-foreground">
          <span className="truncate">{t(vertical.label)}</span>
        </span>
      </div>

      <NavList items={items} onNavigate={onNavigate} />

      <div className="mt-auto rounded-lg border border-border bg-surface px-3 py-3 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">Plan</span>
          <span className="truncate font-semibold text-foreground">{usage.plan.name}</span>
        </div>
        {limit ? (
          <>
            <ShareBar used={used} limit={limit} label={voice ? "Call minutes used this month" : "Chats used this month"} className="mt-2" />
            <p className="mt-1.5 text-muted-foreground">
              <span className="tabular-nums text-foreground">{minutes(used)}</span> of <span className="tabular-nums">{minutes(limit)}</span> {unit} used
            </p>
          </>
        ) : (
          <p className="mt-1.5 text-muted-foreground">
            <span className="tabular-nums text-foreground">{minutes(used)}</span> {unit} used this month
          </p>
        )}
      </div>
    </div>
  );
}

function AccountActions() {
  const router = useRouter();
  const toast = useAppToast();
  const { merchant } = useWorkspace();
  return (
    <div className="flex items-center gap-1 md:gap-2">
      <Link
        href="/settings"
        className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted-foreground hover:text-foreground lg:inline-flex"
      >
        <UserRound className="h-4 w-4" aria-hidden="true" />
        <span className="max-w-48 truncate">{merchant.owner_name || merchant.username}</span>
      </Link>
      <Button
        variant="ghost"
        size="sm"
        aria-label="Log out"
        onClick={() => {
          clearMerchantSession();
          toast.success("Logged out.");
          router.replace("/login");
        }}
      >
        <LogOut className="h-4 w-4" aria-hidden="true" />
        <span className="hidden sm:inline">Log out</span>
      </Button>
    </div>
  );
}

/** Header, sidebar and mobile drawer for every signed-in account page. */
export function MerchantShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-card px-3 py-2 text-sm font-medium focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card md:hidden"
              aria-label="Open navigation"
              aria-expanded={open}
              aria-controls="merchant-drawer"
              onClick={() => setOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </button>
            <Link href="/dashboard" className="flex min-w-0 items-center gap-3">
              <BanglaBotMark compact />
              <BanglaBotBrand subtitle="Account portal" />
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <AccountActions />
          </div>
        </div>
      </header>
      <div className="flex min-h-[calc(100vh-61px)]">
        <aside className="hidden w-60 shrink-0 border-r border-border bg-card md:block">
          <div className="sticky top-[61px] h-[calc(100vh-61px)] overflow-y-auto p-3">
            <SidebarContent />
          </div>
        </aside>
        <main id="main" className="min-w-0 flex-1 px-4 py-6 md:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 md:hidden" id="merchant-drawer" role="dialog" aria-modal="true" aria-label="Navigation">
          <button type="button" tabIndex={-1} className="absolute inset-0 bg-foreground/30" aria-label="Close navigation" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">Menu</span>
              <button
                ref={closeRef}
                type="button"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close navigation"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <SidebarContent onNavigate={() => setOpen(false)} />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
