/** Self-serve purchase (public): the catalog, live quotes, signup → checkout, status, email verification. */

import { queryString, request } from "./client";
import type { BillingInterval, CatalogAddon, PlanSelection, Quote, Tier } from "./billing";
import type { Direction, Label, Region } from "./types";

export type SignupCatalog = {
  verticals: { key: string; label: Partial<Label>; description: Partial<Label>; directions: Direction[] }[];
  plans: Tier[];
  addons: CatalogAddon[];
  regions: Region[];
  billing: { currency: string; intervals: BillingInterval[]; annual_months: number };
};

export type SignupInput = PlanSelection & {
  business_name: string;
  owner_name: string;
  email: string;
  phone: string;
  /** 10+ characters. */
  password: string;
  region: string;
  vertical: string;
  username?: string;
  /** Honeypot: a hidden field real visitors never fill. */
  website: string;
};

export type SignupStatus = "pending_payment" | "awaiting_approval" | "approved" | "rejected";

export const signupApi = {
  /** Offered business types; with `vertical`, only the tiers / add-ons sold for it. */
  catalog: (vertical = "") => request<SignupCatalog>(`/api/public/catalog${queryString({ vertical })}`),
  quote: (selection: PlanSelection & { vertical: string }) =>
    request<Quote>("/api/public/signup/quote", { method: "POST", body: JSON.stringify(selection) }),
  /** 422 validation / password policy, 409 duplicate, 429 slow down, 503 payments unavailable. */
  signup: (values: SignupInput) =>
    request<{ checkout_url: string | null; reference: string; status: SignupStatus }>("/api/public/signup", { method: "POST", body: JSON.stringify(values) }),
  status: (reference: string) =>
    request<{ status: SignupStatus; email_verified: boolean; paid: boolean }>(`/api/public/signup/status${queryString({ reference })}`),
  verifyEmail: (token: string) =>
    request<{ verified: boolean; status: SignupStatus }>("/api/public/signup/verify-email", { method: "POST", body: JSON.stringify({ token }) }),
};
