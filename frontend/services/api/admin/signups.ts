/** Self-serve signups waiting for payment or approval. Backend: backend/app/api/routes/admin_plans.py
 * (superadmin, support). */

import { queryString, request } from "../client";
import type { CursorPage, CursorParams } from "./common";

export type SignupStatus = "pending_payment" | "awaiting_approval" | "approved" | "rejected";

export type Signup = {
  id: string;
  merchant_id: string;
  business_name: string;
  owner_name: string;
  email: string;
  phone: string;
  region: string;
  vertical: string;
  tier: string;
  status: SignupStatus;
  account_active: boolean;
  email_verified: boolean;
  /** Present while the email is unverified (no mail provider yet: pass it on by hand). */
  verify_url: string;
  paid_at: string | null;
  subscription: { id: string; status: string; amount: number; currency: string; interval: string } | null;
  ip: string | null;
  admin_note: string;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
};

export type SignupDecision = { note?: string; /** Approve: activate as paid offline. */ mark_paid?: boolean };

export const signupsApi = {
  list: (params: CursorParams & { status?: SignupStatus | "" } = {}) =>
    request<CursorPage<Signup>>(`/api/admin/signups${queryString(params)}`, { auth: "admin" }),
  decide: (merchantId: string, decision: "approve" | "reject", body: SignupDecision = {}) =>
    request<Signup>(`/api/admin/signups/${encodeURIComponent(merchantId)}/${decision}`, {
      method: "POST",
      auth: "admin",
      body: JSON.stringify({ note: body.note ?? "", mark_paid: Boolean(body.mark_paid) }),
    }),
};
