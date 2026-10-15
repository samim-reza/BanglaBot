/** The audit log, newest first. Backend: backend/app/api/routes/admin_audit.py (superadmin, support). */

import { queryString, request } from "../client";
import type { CursorPage, CursorParams } from "./common";

export type AuditActorType = "admin" | "merchant" | "system";

export type AuditEvent = {
  id: string;
  at: string;
  actor_type: AuditActorType | string;
  /** An admin user id, `env:<name>`, or a merchant id. */
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  merchant_id: string | null;
  ip: string | null;
  meta: Record<string, unknown>;
};

export type AuditParams = CursorParams & {
  /** Exact action, or a prefix ending in "*" (e.g. "admin.*"). */
  action?: string;
  merchant_id?: string;
  actor?: string;
  actor_type?: AuditActorType | "";
};

export const auditApi = {
  list: (params: AuditParams = {}) => request<CursorPage<AuditEvent>>(`/api/admin/audit${queryString(params)}`, { auth: "admin" }),
};
