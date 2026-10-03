/** Account owner: authentication, workspace, settings and add-on keys. */

import { request } from "./client";
import type { FlowPreview, Merchant, MerchantSettingsInput, Workspace } from "./types";

export const merchantApi = {
  login: (username: string, password: string) =>
    request<{ token: string; merchant: Merchant }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<Merchant>("/api/auth/me", { auth: "merchant" }),
  /** Account + its business engine spec + usage — everything the portal renders from. */
  workspace: () => request<Workspace>("/api/auth/workspace", { auth: "merchant" }),
  updateMe: (values: MerchantSettingsInput) =>
    request<Merchant>("/api/auth/me", { method: "PATCH", auth: "merchant", body: JSON.stringify(values) }),
  changePassword: (current_password: string, new_password: string) =>
    request<unknown>("/api/auth/change-password", {
      method: "POST",
      auth: "merchant",
      body: JSON.stringify({ current_password, new_password }),
    }),
  flowPreview: () => request<FlowPreview>("/api/auth/flow-preview", { auth: "merchant" }),
  /** New website-widget key (the old embed snippet stops working). */
  rotateWidgetKey: () => request<Merchant>("/api/auth/me/widget-key", { method: "POST", auth: "merchant" }),
  rotateWebhookSecret: () => request<Merchant>("/api/auth/me/webhook-secret", { method: "POST", auth: "merchant" }),
  testWebhook: () =>
    request<{ ok: boolean; status?: number; error?: string }>("/api/auth/me/webhook-test", { method: "POST", auth: "merchant" }),
};
