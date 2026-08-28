/** Merchant authentication and settings. */

import { request } from "./client";
import type { Merchant, MerchantSettingsInput } from "./types";

export const merchantApi = {
  login: (username: string, password: string) =>
    request<{ token: string; merchant: Merchant }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<Merchant>("/api/auth/me", { auth: "merchant" }),
  updateMe: (values: MerchantSettingsInput) =>
    request<Merchant>("/api/auth/me", { method: "PATCH", auth: "merchant", body: JSON.stringify(values) }),
  changePassword: (current_password: string, new_password: string) =>
    request<unknown>("/api/auth/change-password", {
      method: "POST",
      auth: "merchant",
      body: JSON.stringify({ current_password, new_password }),
    }),
  flowPreview: () => request<{ steps: string[] }>("/api/auth/flow-preview", { auth: "merchant" }),
};
