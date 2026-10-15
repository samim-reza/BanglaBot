"use client";

import Link from "next/link";
import {
  AudioLines,
  Building2,
  ClipboardList,
  CreditCard,
  ExternalLink,
  Inbox,
  LayoutDashboard,
  MessagesSquare,
  Package,
  Puzzle,
  Radio,
  ScrollText,
  Server,
  UserCheck,
  UserCog,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

import { useAdminMe } from "./admin-me";
import type { Permission } from "./permissions";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: "inquiries" | "requests" | "signups";
  /** Hidden unless the admin's role has it. */
  permission?: Permission;
  /** Label for roles without `permission` (the item stays visible). */
  fallbackLabel?: string;
};

const NAV: { label: string; items: NavItem[] }[] = [
  {
    label: "Console",
    items: [
      { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
      { href: "/admin/live", label: "Live calls", icon: Radio },
      { href: "/admin/merchants", label: "Accounts", icon: Building2 },
      { href: "/admin/calls", label: "Calls", icon: MessagesSquare },
      { href: "/admin/orders", label: "Records", icon: ClipboardList },
      { href: "/admin/finance", label: "Finance", icon: Wallet, permission: "finance" },
      { href: "/admin/plans", label: "Plans & add-ons", icon: Package },
      { href: "/admin/subscriptions", label: "Subscriptions", icon: CreditCard, permission: "subscriptions" },
      { href: "/admin/voice", label: "Voice engine", icon: AudioLines },
      { href: "/admin/audit", label: "Audit log", icon: ScrollText, permission: "audit" },
      { href: "/admin/admins", label: "Admins", icon: UserCog, permission: "manageAdmins", fallbackLabel: "My account" },
      { href: "/admin/system", label: "System", icon: Server },
    ],
  },
  {
    label: "Inbox",
    items: [
      { href: "/admin/signups", label: "Signups", icon: UserCheck, badge: "signups", permission: "signups" },
      { href: "/admin/requests", label: "Add-on requests", icon: Puzzle, badge: "requests" },
      { href: "/admin/inquiries", label: "Sales inquiries", icon: Inbox, badge: "inquiries" },
    ],
  },
];

const ITEM =
  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function NavList({
  pathname,
  counts,
  onNavigate,
}: {
  pathname: string;
  counts: { inquiries: number; requests: number; signups: number };
  onNavigate?: () => void;
}) {
  const { can, loading } = useAdminMe();
  return (
    <nav aria-label="Admin console" className="flex flex-col gap-4">
      {NAV.map((group) => (
        <div key={group.label} className="flex flex-col gap-0.5">
          <p className="mb-1 px-3 text-[12px] font-semibold text-muted-foreground">{group.label}</p>
          {group.items.map((item) => {
            const allowed = !item.permission || can(item.permission);
            if (!allowed && (!item.fallbackLabel || loading)) return null;
            const label = allowed ? item.label : item.fallbackLabel!;
            const active = item.href === "/admin" ? pathname === "/admin" : pathname === item.href || pathname.startsWith(`${item.href}/`);
            const count = item.badge ? counts[item.badge] : 0;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(ITEM, active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground")}
              >
                <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="flex-1">{label}</span>
                {count > 0 && (
                  <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-bold leading-none text-primary-foreground">
                    {count > 99 ? "99+" : count}
                    <span className="sr-only">{item.badge === "inquiries" ? " new" : " waiting"}</span>
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function WebsiteLink({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link href="/" target="_blank" rel="noopener" onClick={onNavigate} className={cn(ITEM, "text-muted-foreground hover:bg-accent hover:text-accent-foreground")}>
      <ExternalLink className="h-4 w-4 shrink-0" aria-hidden="true" />
      Public website
      <span className="sr-only">(opens in a new tab)</span>
    </Link>
  );
}
