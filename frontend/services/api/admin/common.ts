/** Shapes shared by the admin console's API modules. */

/** Console roles. superadmin: everything · support: accounts, calls, flows, audit · finance: money views. */
export type AdminRole = "superadmin" | "support" | "finance";

export const ADMIN_ROLES: AdminRole[] = ["superadmin", "support", "finance"];

/** A cursor page: pass `next_cursor` back as `cursor`; `null` means the end. */
export type CursorPage<T> = { items: T[]; next_cursor: string | null };

export type CursorParams = { cursor?: string; limit?: number };
