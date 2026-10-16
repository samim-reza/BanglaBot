/** Finance: cost, revenue, margin, breakdowns, per-account economics, per-call cost lines, the price
 * book, daily spend caps, forecast and CSV export. Backend: backend/app/api/routes/admin_finance.py,
 * app/schemas/finance.py (superadmin + finance). `month` is YYYY-MM (UTC); empty = this month.
 * Free-tier usage costs $0 with a "list" (shadow) cost — the console shows both. */

import { queryString, rawRequest, request } from "../client";
import type { CursorParams } from "./common";

export type FinanceMonth = { month: string; period_start: string; period_end: string };

export type CategoryCost = { category: string; cost_usd: number; list_cost_usd: number };

export type FinanceOverview = FinanceMonth & {
  fraction_elapsed: number;
  cost_usd: number;
  list_cost_usd: number;
  revenue_usd: number;
  margin_usd: number;
  /** 0–1; null without revenue. */
  margin_pct: number | null;
  minutes: number;
  calls: number;
  chats: number;
  cost_per_minute_usd: number | null;
  cache_savings_usd: number;
  free_tier_savings_usd: number;
  accounts: number;
  paying_accounts: number;
  by_category: CategoryCost[];
};

export type BreakdownBy = "category" | "provider" | "model" | "vertical" | "account";

export type BreakdownItem = {
  key: string;
  label: string;
  cost_usd: number;
  list_cost_usd: number;
  cache_savings_usd: number;
  free_tier_savings_usd: number;
  share_pct: number;
  events: number;
  category?: string | null;
  provider?: string | null;
};

export type FinanceBreakdown = FinanceMonth & { by: BreakdownBy; total_cost_usd: number; items: BreakdownItem[] };

export type AccountFinance = {
  merchant_id: string;
  business_name: string;
  vertical: string;
  plan: string;
  active: boolean;
  minutes: number;
  calls: number;
  chats: number;
  cost_usd: number;
  list_cost_usd: number;
  revenue_usd: number;
  margin_usd: number;
  margin_pct: number | null;
  cost_per_minute_usd: number | null;
  cache_savings_usd: number;
  free_tier_savings_usd: number;
  revenue?: Record<string, unknown> | null;
};

export type AccountFinancePage = FinanceMonth & { items: AccountFinance[]; next_cursor: string | null };

export type CostLine = {
  category: string;
  provider: string;
  sku: string;
  unit: string;
  /** Decimal strings. */
  quantity: string;
  unit_cost: string;
  cost_usd: number;
  list_cost_usd: number;
  free_tier: boolean;
  cache_hit: boolean;
  meta: Record<string, unknown>;
};

export type CallCosts = {
  call_log_id: string;
  merchant_id: string;
  direction: string;
  flow: string;
  duration_secs: number;
  created_at: string | null;
  /** False for calls before metering existed. */
  metered: boolean;
  lines: CostLine[];
  cost_usd: number;
  list_cost_usd: number;
  cache_savings_usd: number;
  free_tier_savings_usd: number;
  by_category: Record<string, number>;
};

export type FinanceForecast = FinanceMonth & {
  fraction_elapsed: number;
  cost_mtd_usd: number;
  cost_forecast_usd: number;
  revenue_mtd_usd: number;
  revenue_forecast_usd: number;
  margin_forecast_usd: number;
  margin_forecast_pct: number | null;
  minutes_mtd: number;
  minutes_forecast: number;
  by_category: { category: string; cost_mtd_usd: number; cost_forecast_usd: number }[];
};

export type Price = {
  key: string;
  provider: string;
  sku: string;
  category: string;
  unit: string;
  per: number;
  /** Decimal strings (USD per `per` units). */
  unit_cost: string;
  list_price: string;
  free_tier: boolean;
  increment_secs: number;
  note: string;
};

export type PricebookVersion = { effective_from: string; prices: Record<string, Record<string, unknown>>; note: string; created_by: string; created_at: string };

export type Pricebook = { at: string; effective_from: string; version: number; prices: Price[]; versions: PricebookVersion[] };

export type PriceOverride = {
  provider: string;
  sku: string;
  unit_cost?: string | number;
  list_price?: string | number;
  free_tier?: boolean;
  increment_secs?: number;
  note?: string;
  /** Only for a SKU the defaults don't know. */
  category?: string;
  unit?: string;
  per?: number;
};

export type ProviderCap = { provider: string; cap_usd: string | null; spent_today_usd: string; over_cap: boolean };

const BASE = "/api/admin/finance";
const month = (value?: string) => (value ? { month: value } : {});

export const financeApi = {
  overview: (m?: string) => request<FinanceOverview>(`${BASE}/overview${queryString(month(m))}`, { auth: "admin" }),
  breakdown: (by: BreakdownBy, m?: string, limit = 50) =>
    request<FinanceBreakdown>(`${BASE}/breakdown${queryString({ by, ...month(m), limit })}`, { auth: "admin" }),
  accounts: (params: CursorParams & { month?: string } = {}) => request<AccountFinancePage>(`${BASE}/accounts${queryString(params)}`, { auth: "admin" }),
  callCosts: (callLogId: string) => request<CallCosts>(`${BASE}/calls/${encodeURIComponent(callLogId)}/costs`, { auth: "admin" }),
  forecast: (m?: string) => request<FinanceForecast>(`${BASE}/forecast${queryString(month(m))}`, { auth: "admin" }),
  pricebook: (at?: string) => request<Pricebook>(`${BASE}/pricebook${queryString({ at })}`, { auth: "admin" }),
  /** A new version effective from `effective_from` (default today, UTC); only the changed prices. */
  savePricebook: (body: { effective_from?: string; note?: string; prices: PriceOverride[] }) =>
    request<Pricebook>(`${BASE}/pricebook`, { method: "PUT", auth: "admin", body: JSON.stringify(body) }),
  caps: () => request<{ items: ProviderCap[] }>(`${BASE}/caps`, { auth: "admin" }),
  /** provider → daily USD cap; null removes the cap, 0 blocks the provider. */
  saveCaps: (caps: Record<string, string | number | null>) =>
    request<{ items: ProviderCap[] }>(`${BASE}/caps`, { method: "PUT", auth: "admin", body: JSON.stringify({ caps }) }),
  /** The CSV as a Blob (the endpoint needs the bearer token, so a plain link won't do). */
  exportCsv: async (kind: "daily" | "accounts", m?: string) => {
    const response = await rawRequest(`${BASE}/export.csv${queryString({ kind, ...month(m) })}`, { auth: "admin" });
    const disposition = response.headers.get("content-disposition") ?? "";
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `callisa-finance-${kind}.csv`;
    return { blob: await response.blob(), filename };
  },
};

/** The overview, or null when the role can't see finance. */
export async function financeOverviewOrNull(m?: string): Promise<FinanceOverview | null> {
  try {
    return await financeApi.overview(m);
  } catch (err) {
    const status = (err as { status?: number } | null)?.status;
    if (status === 403 || status === 404) return null;
    throw err;
  }
}
