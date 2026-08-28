/** Platform admin console: merchants, and every order and call across them. */

import { queryString, request } from "./client";
import type {
  AdminOverview,
  CallLog,
  Merchant,
  MerchantAdminUpdate,
  MerchantCreateInput,
  Order,
  OrderStatus,
  Page,
} from "./types";

export type AdminOrderParams = { merchant_id?: string; status?: OrderStatus | ""; page?: number; page_size?: number };
export type AdminCallParams = { merchant_id?: string; page?: number; page_size?: number };

export const adminApi = {
  login: (username: string, password: string) =>
    request<{ token: string }>("/api/admin/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  overview: () => request<AdminOverview>("/api/admin/overview", { auth: "admin" }),
  merchants: () => request<Merchant[]>("/api/admin/merchants", { auth: "admin" }),
  merchant: (id: string) => request<Merchant>(`/api/admin/merchants/${encodeURIComponent(id)}`, { auth: "admin" }),
  createMerchant: (values: MerchantCreateInput) =>
    request<Merchant>("/api/admin/merchants", { method: "POST", auth: "admin", body: JSON.stringify(values) }),
  updateMerchant: (id: string, values: MerchantAdminUpdate) =>
    request<Merchant>(`/api/admin/merchants/${encodeURIComponent(id)}`, {
      method: "PATCH",
      auth: "admin",
      body: JSON.stringify(values),
    }),
  deleteMerchant: (id: string) =>
    request<void>(`/api/admin/merchants/${encodeURIComponent(id)}`, { method: "DELETE", auth: "admin" }),
  orders: (params: AdminOrderParams = {}) =>
    request<Page<Order>>(`/api/admin/orders${queryString(params)}`, { auth: "admin" }),
  calls: (params: AdminCallParams = {}) =>
    request<Page<CallLog>>(`/api/admin/calls${queryString(params)}`, { auth: "admin" }),
};
