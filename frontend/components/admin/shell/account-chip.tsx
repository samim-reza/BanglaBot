"use client";

import Link from "next/link";
import { ShieldCheck } from "lucide-react";

import { useAdminMe } from "./admin-me";
import { ROLE_LABELS } from "./permissions";

/** Signed-in admin and role in the header; links to My account. */
export function AccountChip() {
  const { me } = useAdminMe();
  if (!me) return null;
  return (
    <Link
      href="/admin/admins#me"
      title="My account"
      className="hidden items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:flex"
    >
      <span className="max-w-[10rem] truncate font-medium">{me.username}</span>
      <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11.5px] font-semibold text-accent-foreground">
        {me.totp_enabled && <ShieldCheck className="h-3 w-3" aria-label="Two-factor on" />}
        {ROLE_LABELS[me.role] ?? me.role}
      </span>
    </Link>
  );
}
