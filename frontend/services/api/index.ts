/** The API client, as a package. Import from `@/services/api`. */

export { API_BASE, ApiRequestError, formatApiError, isApiRequestError, queryString, rawRequest, request } from "./client";
export type { AuthScope, RequestOptions } from "./client";

export {
  adminToken,
  clearAdminSession,
  clearMerchantSession,
  getMerchantSession,
  merchantToken,
  saveAdminSession,
  saveMerchantProfile,
  saveMerchantSession,
} from "./session";

export * from "./types";

export { merchantApi } from "./merchant";
export { ordersApi } from "./orders";
export type { OrderListParams } from "./orders";
export { adminApi } from "./admin";
export type { AdminCallParams, AdminOrderParams } from "./admin";
