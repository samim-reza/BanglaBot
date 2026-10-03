/** Account records (orders / appointments / leads / bookings) and outbound calls. */

import { queryString, rawRequest, request } from "./client";
import type { BulkCallStatus, Order, OrderDetail, OrderInput, OrderStats, OrderStatus, OrderUpdate, Page } from "./types";

export type OrderListParams = {
  page?: number;
  page_size?: number;
  status?: OrderStatus | "";
  search?: string;
  kind?: string;
  /** Only records scheduled from now on. */
  upcoming?: boolean;
  sort?: "created" | "scheduled";
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
  /** Place an outbound call about this record (confirmation / reminder / follow-up). */
  call: (id: string) => request<Order>(`/api/orders/${encodeURIComponent(id)}/call`, { method: "POST", auth: "merchant" }),
  /** Bulk dialing: status of the current/last "Call all" run plus the auto-call schedule. */
  callAllStatus: () => request<BulkCallStatus>("/api/orders/call-all", { auth: "merchant" }),
  /** Dial every record that still needs a call (pending / no answer), a few at a time. */
  callAll: () => request<BulkCallStatus>("/api/orders/call-all", { method: "POST", auth: "merchant", body: "{}" }),
  cancelCallAll: () => request<BulkCallStatus>("/api/orders/call-all/cancel", { method: "POST", auth: "merchant" }),
  /** `at` is an ISO-8601 timestamp (UTC); repeat_daily re-arms it for the next day after it fires. */
  setAutoCall: (at: string, repeat_daily: boolean) =>
    request<BulkCallStatus>("/api/orders/call-all/schedule", {
      method: "PUT",
      auth: "merchant",
      body: JSON.stringify({ at, repeat_daily }),
    }),
  clearAutoCall: () => request<BulkCallStatus>("/api/orders/call-all/schedule", { method: "DELETE", auth: "merchant" }),
  /** Fetch a recording with the bearer header and return an object URL for <audio>. */
  recordingObjectUrl: async (logId: string) => {
    const response = await rawRequest(`/api/orders/recordings/${encodeURIComponent(logId)}`, { auth: "merchant" });
    return URL.createObjectURL(await response.blob());
  },
};
