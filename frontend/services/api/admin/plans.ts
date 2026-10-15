/** Plans & add-ons: the tier + add-on catalog editor, signup settings and the business types offered.
 * Backend: backend/app/api/routes/admin_plans.py, app/schemas/plans.py. Money = JSON numbers in USD. */

import { request } from "../client";
import type { Label } from "../types";

export type FlowEditing = "lines" | "full";

export type TierLimits = {
  max_concurrent_calls: number;
  flow_editing: FlowEditing | string;
  payments: boolean;
  custom_fields: boolean;
  api_webhooks: boolean;
};

export type CatalogTier = {
  key: string;
  name: string;
  tagline: string;
  product: "voice" | "chat";
  price_month: number;
  /** 0 = 10 × the monthly price. */
  price_year: number;
  overage_per_minute: number;
  included_minutes: number;
  included_chats: number;
  included_sms: number;
  phone_numbers: number;
  included_languages: number;
  channels: string[];
  includes: string[];
  /** Marketing bullets. */
  features: string[];
  limits: TierLimits;
  /** Empty = every business type. */
  verticals: string[];
  visible: boolean;
  checkout: boolean;
  highlight: boolean;
  trial_days: number;
  sort: number;
  [extra: string]: unknown;
};

export type CatalogAddon = {
  key: string;
  name: string;
  category: string;
  price: number;
  period: "month" | "once";
  /** Read-only, computed by the server ("$29 / mo"). */
  price_label?: string;
  summary: string;
  stackable: boolean;
  max_quantity: number;
  channel: string;
  feature: string;
  /** Per unit, e.g. {minutes: 100}. */
  grants: Record<string, number>;
  products: string[];
  verticals: string[];
  visible: boolean;
  sort: number;
  [extra: string]: unknown;
};

export type CatalogOptions = {
  channels: { key: string; label: string }[];
  features: string[];
  capabilities: string[];
  grants: string[];
  categories: string[];
  periods: string[];
  products: string[];
  flow_editing: string[];
  verticals: string[];
};

export type PlanCatalog = {
  tiers: CatalogTier[];
  addons: CatalogAddon[];
  defaults: { tiers: CatalogTier[]; addons: CatalogAddon[] };
  options: CatalogOptions;
};

export type SignupSettings = { auto_activate: boolean; require_verified_email: boolean };

export type OfferedVertical = { key: string; label: Partial<Label>; description: Partial<Label>; offered: boolean };

export const plansApi = {
  catalog: () => request<PlanCatalog>("/api/admin/plans/catalog", { auth: "admin" }),
  /** The FULL catalog (superadmin). Keys still in use can't be removed — hide them (`visible: false`). */
  saveCatalog: (tiers: CatalogTier[], addons: CatalogAddon[]) =>
    request<PlanCatalog>("/api/admin/plans/catalog", { method: "PUT", auth: "admin", body: JSON.stringify({ tiers, addons }) }),
  settings: () => request<SignupSettings>("/api/admin/plans/settings", { auth: "admin" }),
  saveSettings: (values: SignupSettings) =>
    request<SignupSettings>("/api/admin/plans/settings", { method: "PUT", auth: "admin", body: JSON.stringify(values) }),
  verticals: () => request<{ items: OfferedVertical[] }>("/api/admin/verticals", { auth: "admin" }),
  saveVerticals: (offered: string[]) =>
    request<{ items: OfferedVertical[] }>("/api/admin/verticals", { method: "PUT", auth: "admin", body: JSON.stringify({ offered }) }),
};
