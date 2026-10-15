/** Admin users (superadmin) and the signed-in admin's own account: password, sessions, two-factor sign-in.
 * Backend: backend/app/api/routes/admin_users.py */

import { queryString, request } from "../client";
import type { AdminRole, CursorPage, CursorParams } from "./common";

export type AdminUser = {
  id: string;
  username: string;
  role: AdminRole;
  active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
};

/** GET /me. `setup_login`: signed in with the env login (no admin users yet) — /me actions answer 409. */
export type AdminMe = Partial<AdminUser> & {
  id: string;
  username: string;
  role: AdminRole;
  totp_enabled: boolean;
  setup_login: boolean;
};

export type AdminUserCreate = { username: string; password: string; role: AdminRole };
export type AdminUserUpdate = { role?: AdminRole; active?: boolean; password?: string; reset_totp?: boolean };
export type TotpSetup = { secret: string; otpauth_uri: string };
/** Password change / sign-out-everywhere hand back a fresh token for this browser. */
export type TokenRefresh = { ok: true; token: string };

const BASE = "/api/admin/users";
const json = (body: unknown) => JSON.stringify(body);

export const adminUsersApi = {
  me: () => request<AdminMe>(`${BASE}/me`, { auth: "admin" }),
  changePassword: (current_password: string, new_password: string) =>
    request<TokenRefresh>(`${BASE}/me/password`, { method: "POST", auth: "admin", body: json({ current_password, new_password }) }),
  logoutAll: () => request<TokenRefresh>(`${BASE}/me/logout-all`, { method: "POST", auth: "admin" }),
  totpSetup: () => request<TotpSetup>(`${BASE}/me/totp/setup`, { method: "POST", auth: "admin" }),
  totpEnable: (code: string) => request<AdminUser>(`${BASE}/me/totp/enable`, { method: "POST", auth: "admin", body: json({ code }) }),
  totpDisable: (code: string) => request<AdminUser>(`${BASE}/me/totp/disable`, { method: "POST", auth: "admin", body: json({ code }) }),

  list: (params: CursorParams = {}) => request<CursorPage<AdminUser>>(`${BASE}${queryString(params)}`, { auth: "admin" }),
  create: (values: AdminUserCreate) => request<AdminUser>(BASE, { method: "POST", auth: "admin", body: json(values) }),
  update: (id: string, values: AdminUserUpdate) =>
    request<AdminUser>(`${BASE}/${encodeURIComponent(id)}`, { method: "PATCH", auth: "admin", body: json(values) }),
  remove: (id: string) => request<void>(`${BASE}/${encodeURIComponent(id)}`, { method: "DELETE", auth: "admin" }),
};
