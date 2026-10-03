/** Platform admin console: accounts, every record and call across them, sales inquiries. */

import { queryString, request } from "./client";
import type {
  AdminMerchantDetail,
  AdminMeta,
  AdminOverview,
  CallChannel,
  CallLog,
  Merchant,
  MerchantAdminUpdate,
  MerchantCreateInput,
  Order,
  OrderStatus,
  Page,
  SalesInquiry,
  SalesInquiryStatus,
} from "./types";

export type AdminOrderParams = { merchant_id?: string; status?: OrderStatus | ""; page?: number; page_size?: number };
export type AdminCallParams = { merchant_id?: string; direction?: CallChannel | ""; page?: number; page_size?: number };
export type AdminInquiryParams = { status?: SalesInquiryStatus | ""; page?: number; page_size?: number };

export const adminApi = {
  login: (username: string, password: string) =>
    request<{ token: string }>("/api/admin/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  /** Business engines, regions, plans and languages for the account forms. */
  meta: () => request<AdminMeta>("/api/admin/meta", { auth: "admin" }),
  overview: () => request<AdminOverview>("/api/admin/overview", { auth: "admin" }),
  merchants: () => request<Merchant[]>("/api/admin/merchants", { auth: "admin" }),
  merchant: (id: string) => request<AdminMerchantDetail>(`/api/admin/merchants/${encodeURIComponent(id)}`, { auth: "admin" }),
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
  /** A 2-hour owner session for this account (open its portal to set it up). */
  impersonate: (id: string) =>
    request<{ token: string; merchant: Merchant }>(`/api/admin/merchants/${encodeURIComponent(id)}/impersonate`, {
      method: "POST",
      auth: "admin",
    }),
  orders: (params: AdminOrderParams = {}) =>
    request<Page<Order>>(`/api/admin/orders${queryString(params)}`, { auth: "admin" }),
  calls: (params: AdminCallParams = {}) =>
    request<Page<CallLog>>(`/api/admin/calls${queryString(params)}`, { auth: "admin" }),
  inquiries: (params: AdminInquiryParams = {}) =>
    request<Page<SalesInquiry>>(`/api/admin/inquiries${queryString(params)}`, { auth: "admin" }),
  updateInquiry: (id: string, values: { status?: SalesInquiryStatus; admin_notes?: string }) =>
    request<SalesInquiry>(`/api/admin/inquiries/${encodeURIComponent(id)}`, {
      method: "PATCH",
      auth: "admin",
      body: JSON.stringify(values),
    }),
  deleteInquiry: (id: string) =>
    request<void>(`/api/admin/inquiries/${encodeURIComponent(id)}`, { method: "DELETE", auth: "admin" }),
};
