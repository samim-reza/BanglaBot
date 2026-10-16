import type { AdminRole } from "@/services/api/admin/common";

/**
 * What each console role may do — mirrors the backend's `require_admin(...)` guards, so the console
 * hides what the API would answer 403 for. Any role may read the rest.
 */
export const PERMISSIONS = {
  hangUp: ["superadmin", "support"],
  editAccounts: ["superadmin", "support"],
  deleteAccounts: ["superadmin"],
  audit: ["superadmin", "support"],
  manageAdmins: ["superadmin"],
  impersonate: ["superadmin", "support"],
  editFlow: ["superadmin", "support"],
  lockFlow: ["superadmin"],
  providers: ["superadmin"],
  voiceTests: ["superadmin"],
  editCatalog: ["superadmin"],
  signups: ["superadmin", "support"],
  subscriptions: ["superadmin", "support", "finance"],
  finance: ["superadmin", "finance"],
} satisfies Record<string, AdminRole[]>;

export type Permission = keyof typeof PERMISSIONS;

export const ROLE_LABELS: Record<AdminRole, string> = {
  superadmin: "Superadmin",
  support: "Support",
  finance: "Finance",
};
