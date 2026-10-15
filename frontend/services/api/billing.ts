/** The owner's plan: what they have, what a change costs, buying it, cancelling, renewing, history. */

import { queryString, request } from "./client";
import type { AddonItem, ChannelKey, Entitlements } from "./types";

export type BillingInterval = "month" | "year";

export type TierLimits = {
  max_concurrent_calls: number;
  flow_editing: "lines" | "full";
  payments: boolean;
  custom_fields: boolean;
  api_webhooks: boolean;
};

/** A plan tier as the catalog / plan view sends it. Money = numbers in USD. */
export type Tier = {
  key: string;
  name: string;
  tagline: string;
  product: "voice" | "chat";
  price_month: number;
  price_year: number;
  overage_per_minute?: number;
  included_minutes: number;
  included_chats: number;
  included_sms: number;
  phone_numbers: number;
  included_languages: number;
  channels: ChannelKey[];
  includes: string[];
  features: string[];
  limits: TierLimits;
  verticals: string[];
  visible: boolean;
  /** false = "Talk to sales" (not bought online). */
  checkout: boolean;
  highlight: boolean;
  trial_days: number;
  sort: number;
};

export type CatalogAddon = AddonItem & { max_quantity: number; verticals: string[]; visible: boolean; sort: number };

export type QuoteItem = { kind: "tier" | "addon"; key: string; name: string; quantity: number; unit_price: number; period: string; amount: number };

export type Quote = {
  tier: string;
  tier_name: string;
  interval: BillingInterval;
  currency: string;
  items: QuoteItem[];
  recurring: number;
  one_time: number;
  total: number;
};

/** What a selection would do to the current plan. */
export type PlanChangeKind = "new" | "upgrade" | "downgrade" | "swap" | "same";
export type PlanChange = {
  kind: PlanChangeKind;
  due_now: number;
  effective: "on_payment" | "period_end" | "now";
  effective_at: string | null;
};

/** tier + interval + {add-on key: quantity} (0 = not selected). */
export type PlanSelection = { tier: string; interval: BillingInterval; addons: Record<string, number> };

export type Subscription = {
  id: string;
  tier: string;
  tier_name: string;
  addons: Record<string, number>;
  once_addons: Record<string, number>;
  interval: BillingInterval;
  amount: number;
  recurring_amount: number;
  currency: string;
  status: string;
  kind: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  scheduled_change: Record<string, unknown>;
  line_items: QuoteItem[];
  payment_provider: string;
  payment_ref: string;
  created_at: string | null;
  activated_at: string | null;
  cancelled_at: string | null;
};

export type PlanView = {
  tier: Tier;
  addons: (CatalogAddon & { quantity: number })[];
  entitlements: Entitlements;
  usage: { period_start: string; minutes: number; calls: number; chats: number; sms: number; minutes_left: number | null; overage_minutes: number };
  limits: Entitlements["limits"];
  subscription: Subscription | null;
  renewal: { status: string; renews_at: string | null; ends_at: string | null; amount: number; interval: BillingInterval } | null;
};

/** A cursor page: pass `next_cursor` back as `cursor`; null = the end. */
export type CursorList<T> = { items: T[]; next_cursor: string | null };

const json = (body: unknown) => ({ method: "POST", auth: "merchant" as const, body: JSON.stringify(body) });

export const billingApi = {
  get: () => request<PlanView>("/api/plan", { auth: "merchant" }),
  quote: (selection: PlanSelection) => request<{ quote: Quote; change: PlanChange }>("/api/plan/quote", json(selection)),
  /** 409 = nothing changes. `checkout_url` = pay there (returns to /plan?reference=…); null = done already. */
  change: (selection: PlanSelection) =>
    request<{ quote: Quote; change: PlanChange; checkout_url: string | null; subscription_id: string | null }>("/api/plan/change", json(selection)),
  renew: () => request<{ quote: Quote; checkout_url: string | null; subscription_id: string | null }>("/api/plan/renew", { method: "POST", auth: "merchant" }),
  /** Cancel at the end of the period (keeps the tier until then). */
  cancel: () => request<Subscription>("/api/plan/cancel", { method: "POST", auth: "merchant" }),
  resume: () => request<Subscription>("/api/plan/cancel", { method: "DELETE", auth: "merchant" }),
  subscriptions: (cursor = "", limit = 20) =>
    request<CursorList<Subscription>>(`/api/plan/subscriptions${queryString({ cursor, limit })}`, { auth: "merchant" }),
};
