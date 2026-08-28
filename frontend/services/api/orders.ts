/** Merchant orders and outbound confirmation calls. */

import { queryString, rawRequest, request } from "./client";
import type { Order, OrderDetail, OrderInput, OrderStats, OrderStatus, OrderUpdate, Page } from "./types";

export type OrderListParams = {
  page?: number;
  page_size?: number;
  status?: OrderStatus | "";
  search?: string;
};

export const ordersApi = {
  list: (params: OrderListParams = {}) =>
    request<Page<Order>>(`/api/orders${queryString(params)}`, { auth: "merchant" }),
  stats: () => request<OrderStats>("/api/orders/stats", { auth: "merchant" }),
  get: (id: string) => request<OrderDetail>(`/api/orders/${encodeURIComponent(id)}`, { auth: "merchant" }),
  create: (values: OrderInput) =>
    request<Order>("/api/orders", { method: "POST", auth: "merchant", body: JSON.stringify(values) }),
  update: (id: string, values: OrderUpdate) =>
    request<Order>(`/api/orders/${encodeURIComponent(id)}`, {
      method: "PATCH",
      auth: "merchant",
      body: JSON.stringify(values),
    }),
  remove: (id: string) => request<void>(`/api/orders/${encodeURIComponent(id)}`, { method: "DELETE", auth: "merchant" }),
  call: (id: string) => request<Order>(`/api/orders/${encodeURIComponent(id)}/call`, { method: "POST", auth: "merchant" }),
  /** Fetch a recording with the bearer header and return an object URL for <audio>. */
  recordingObjectUrl: async (logId: string) => {
    const response = await rawRequest(`/api/orders/recordings/${encodeURIComponent(logId)}`, { auth: "merchant" });
    return URL.createObjectURL(await response.blob());
  },
};
