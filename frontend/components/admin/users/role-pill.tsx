import { Pill, type Tone } from "@/components/admin/badges";
import { ROLE_LABELS } from "@/components/admin/shell/permissions";
import type { AdminRole } from "@/services/api/admin/common";

const TONES: Record<AdminRole, Tone> = { superadmin: "violet", support: "blue", finance: "cyan" };

export function RolePill({ role }: { role: AdminRole | string }) {
  return <Pill tone={TONES[role as AdminRole] ?? "neutral"}>{ROLE_LABELS[role as AdminRole] ?? role}</Pill>;
}

export const ROLE_HINTS: Record<AdminRole, string> = {
  superadmin: "Everything, including admins, locks, providers and prices",
  support: "Accounts, calls, flows, signups and the audit log",
  finance: "Finance, subscriptions and read-only views",
};
