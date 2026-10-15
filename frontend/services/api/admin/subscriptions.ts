/** Subscriptions across accounts, newest first. Backend: backend/app/api/routes/admin_plans.py,
 * app/services/subscription_service.py. Money = JSON numbers. */

import { queryString, request } from "../client";
import type { CursorPage, CursorParams } from "./common";

export type SubscriptionStatus = "pending" | "active" | "past_due" | "cancelled";
export type SubscriptionKind = "signup" | "change" | "renewal" | "manual";

export type SubscriptionLineItem = {
  kind: string;
  key: string;
  name: string;
  quantity: number;
  unit_price: number;
  period: string;
  amount: number;
};

export type Subscription = {
  id: string;
  merchant_id: string;
  merchant_name: string;
  tier: string;
  tier_name?: string;
  addons: Record<string, number>;
  once_addons?: Record<string, number>;
  interval: "month" | "year" | string;
  amount: number;
  recurring_amount: number;
  currency: string;
  status: SubscriptionStatus;
  kind: SubscriptionKind;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  scheduled_change?: Record<string, unknown>;
  line_items: SubscriptionLineItem[];
  payment_provider: string | null;
  payment_ref: string | null;
  created_at: string;
  activated_at: string | null;
  cancelled_at?: string | null;
};

export type SubscriptionParams = CursorParams & {
  status?: SubscriptionStatus | "";
  merchant_id?: string;
  tier?: string;
  kind?: SubscriptionKind | "";
};

export const subscriptionsApi = {
  list: (params: SubscriptionParams = {}) => request<CursorPage<Subscription>>(`/api/admin/subscriptions${queryString(params)}`, { auth: "admin" }),
};
