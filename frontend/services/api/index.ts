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
export { catalogApi } from "./catalog";
export { callsApi } from "./calls";
export type { CallListParams } from "./calls";
export { integrationsApi } from "./integrations";
export { addonsApi, channelsApi } from "./addons";
export { publicApi } from "./public";
export { adminApi } from "./admin";
export type { AdminCallParams, AdminInquiryParams, AdminOrderParams } from "./admin";
