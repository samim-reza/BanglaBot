/** Payments: the public test pay page (dummy links) and the owner's payment settings. */

import { request } from "./client";

/** What the public pay page shows. `amount` is a decimal string. */
export type PayPage = {
  reference: string;
  business: string;
  description: string;
  amount: string;
  currency: string;
  /** pending | paid | failed | refunded | expired */
  status: string;
  kind: string;
  provider: string;
  expires_at: string | null;
  paid_at: string | null;
  /** The test page may show its "Pay" button. */
  can_complete: boolean;
};

export type PaymentMethod = "online" | "at_venue";

export type PaymentSettings = {
  /** platform = the platform's links; link = the owner's own link template. */
  provider: "platform" | "link";
  /** https:// URL with {amount}, {currency}, {ref}. */
  link_template: string;
  methods: PaymentMethod[];
  /** What platform links are right now: dummy | stripe. */
  platform_provider: string;
};

export const payApi = {
  /** 404 = invalid or expired link. */
  view: (token: string) => request<PayPage>(`/api/public/pay/${encodeURIComponent(token)}`),
  /** Test phase only: marks the link paid (no money moves). 409 = expired / already settled. */
  complete: (token: string) => request<PayPage>(`/api/public/pay/${encodeURIComponent(token)}/complete`, { method: "POST" }),
};

export const paymentsApi = {
  settings: () => request<PaymentSettings>("/api/payments/settings", { auth: "merchant" }),
  updateSettings: (values: Partial<Omit<PaymentSettings, "platform_provider">>) =>
    request<PaymentSettings>("/api/payments/settings", { method: "PUT", auth: "merchant", body: JSON.stringify(values) }),
};
